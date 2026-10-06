"""
medicine_recommendation_service.py

Two clearly separated recommendation sources:

1. SUPPLIED SNAPSHOT (`recommendations`): the current-state recommendations shipped with the dataset (single date),
   returned as supplied and enriched with the medicine's current stock. Every one carries the supplied `reason`.

2. FORECAST-BASED (`forecast_based`): computed on request from real stored values -- current stock (stock ledger) and the
   latest MODEL-GENERATED forecast run -- using the documented rules below. Nothing is invented; every recommendation
   states its rule, its inputs and why it fired. No procurement quantity is prescribed (only the arithmetic shortfall).

Forecast-based rules (thresholds are documented constants):
  R1 Potential Shortage : forecast demand over the next H days  >  current closing stock.
                          Severity Critical if stock_status is Low/Critical, otherwise Warning.
  R2 Excess Stock       : stock_status is Overstock AND forecast demand over H days <= current stock.
  R3 Demand Increasing  : mean forecast of the last 7 horizon days is > 5% above the first 7 days.
  R4 Demand Decreasing  : same comparison is < -5%.
  R5 Normal Monitoring  : none of the above fired.
"""

from app.config import get_settings
from app.database.db import db_cursor
from app.database.queries import medicine_alert_queries as aq
from app.database.queries import medicine_forecast_queries as fq
from app.services.medicine_common import as_of_date, meta, validate_entities
from app.services.medicine_service import FORECAST_TREND_THRESHOLD, _run_public
from app.utils.errors import BadRequestError
from app.utils.query_helpers import page, resolve_sort, validate_range

REC_SORT = {"severity": "FIELD(r.severity, 'Critical', 'Warning', 'Info')", "date": "r.rec_date",
            "type": "r.recommendation_type", "medicine": "m.medicine_name", "id": "r.recommendation_id"}

RULES = [
    {"rule_id": "R1", "type": "Potential Shortage", "condition": "forecast demand over next H days > current closing stock"},
    {"rule_id": "R2", "type": "Excess Stock", "condition": "stock_status = Overstock AND forecast demand over H days <= current stock"},
    {"rule_id": "R3", "type": "Demand Increasing", "condition": "mean forecast of last 7 horizon days > +5% vs first 7 days"},
    {"rule_id": "R4", "type": "Demand Decreasing", "condition": "mean forecast of last 7 horizon days < -5% vs first 7 days"},
    {"rule_id": "R5", "type": "Normal Monitoring", "condition": "none of R1-R4 applies"},
]


def recommendations(rec_type, severity, medicine_id, category, search, date_from, date_to, sort, order, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, REC_SORT, "severity") + ", r.rec_date DESC, r.recommendation_id"
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = aq.recommendations(cur, as_of, rec_type, severity, medicine_id, category, search, d_from, d_to,
                                         order_sql, limit, offset)
        summary = aq.recommendation_summary(cur, medicine_id, category)
        snap = aq.snapshot_dates(cur)
    items = [{"recommendation_id": r["recommendation_id"], "date": r["rec_date"], "medicine_id": r["medicine_id"],
              "medicine_name": r["medicine_name"], "category": r["category"],
              "recommendation_type": r["recommendation_type"], "severity": r["severity"],
              "why": r["reason"], "recommended_action": r["recommended_action"],
              "current_stock": r["current_stock"], "current_stock_status": r["current_stock_status"],
              "source": "SUPPLIED_SNAPSHOT"} for r in rows]
    return page(items, total, limit, offset, summary=summary,
                snapshot={"recommendation_date_range": [snap["recs_min"], snap["recs_max"]],
                          "note": ("Current-state snapshot supplied with the dataset (single date); not a history. "
                                   "See /recommendations/forecast-based for recommendations that use the model forecast.")},
                meta=meta(as_of))


def forecast_based(horizon_days, medicine_id, category):
    as_of = as_of_date()
    horizon = horizon_days or get_settings().forecast_shortage_horizon_days
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        run = fq.latest_run(cur)
        if not run:
            return {"available": False, "items": [], "total": 0, "rules": RULES,
                    "message": "No model-generated forecast exists yet (run `python -m app.ml.medicine_ml train`).",
                    "meta": meta(as_of)}
        if not 1 <= horizon <= run["horizon_days"]:
            raise BadRequestError(f"horizon_days must be between 1 and {run['horizon_days']}.")
        rows = aq.forecast_recommendation_inputs(cur, as_of, run["run_id"], horizon, medicine_id, category)

    items, skipped = [], []
    for r in rows:
        if r["closing_stock"] is None or r["forecast_total"] is None:
            skipped.append(r["medicine_id"])
            continue
        stock, fc = int(r["closing_stock"]), float(r["forecast_total"])
        status = r["stock_status"]
        base = {"medicine_id": r["medicine_id"], "medicine_name": r["medicine_name"], "category": r["category"],
                "as_of_date": as_of, "forecast_run_id": run["run_id"], "horizon_days": horizon,
                "source": "MODEL_FORECAST_AND_CURRENT_STOCK"}
        inputs = {"current_stock": stock, "stock_status": status, f"forecast_demand_next_{horizon}_days": round(fc, 2),
                  "forecast_avg_daily": round(fc / horizon, 2)}
        fired = []
        if fc > stock:
            shortfall = fc - stock
            fired.append({**base, "rule_id": "R1", "recommendation_type": "Potential Shortage",
                          "severity": "Critical" if status in ("Low", "Critical") else "Warning",
                          "why": (f"Model-forecast demand over the next {horizon} days ({fc:.1f} units) exceeds current "
                                  f"stock ({stock} units, status {status}); projected shortfall {shortfall:.1f} units "
                                  f"before any new receipts."),
                          "recommended_action": "Review replenishment", "inputs": {**inputs, "projected_shortfall": round(shortfall, 2)}})
        elif status == "Overstock":
            fired.append({**base, "rule_id": "R2", "recommendation_type": "Excess Stock", "severity": "Info",
                          "why": (f"Stock ({stock} units) is flagged Overstock and covers the model-forecast demand for "
                                  f"the next {horizon} days ({fc:.1f} units) with {stock - fc:.1f} units to spare."),
                          "recommended_action": "Review excess inventory",
                          "inputs": {**inputs, "stock_minus_forecast": round(stock - fc, 2)}})
        a7, b7 = r["avg_first_7"], r["avg_last_7"]
        if a7 and b7 is not None and float(a7) > 0:
            change = (float(b7) - float(a7)) / float(a7)
            trend_inputs = {**inputs, "forecast_avg_first_7_days": round(float(a7), 2),
                            "forecast_avg_last_7_days": round(float(b7), 2), "forecast_change_percent": round(change * 100, 2)}
            if change > FORECAST_TREND_THRESHOLD:
                fired.append({**base, "rule_id": "R3", "recommendation_type": "Demand Increasing", "severity": "Info",
                              "why": (f"Forecast demand rises {change * 100:.1f}% between the first and last 7 days of the "
                                      f"{run['horizon_days']}-day forecast ({float(a7):.1f} -> {float(b7):.1f} units/day)."),
                              "recommended_action": "Prepare inventory review", "inputs": trend_inputs})
            elif change < -FORECAST_TREND_THRESHOLD:
                fired.append({**base, "rule_id": "R4", "recommendation_type": "Demand Decreasing", "severity": "Info",
                              "why": (f"Forecast demand falls {abs(change) * 100:.1f}% between the first and last 7 days of "
                                      f"the {run['horizon_days']}-day forecast ({float(a7):.1f} -> {float(b7):.1f} units/day)."),
                              "recommended_action": "Monitor for overstock risk", "inputs": trend_inputs})
        if not fired:
            fired.append({**base, "rule_id": "R5", "recommendation_type": "Normal Monitoring", "severity": "Info",
                          "why": (f"Current stock ({stock} units) covers the model-forecast demand for the next {horizon} "
                                  f"days ({fc:.1f} units) and the forecast trend is within +/-5%."),
                          "recommended_action": "No action needed", "inputs": inputs})
        items.extend(fired)
    return {"available": True, "type": "FORECAST_BASED_RECOMMENDATIONS", "items": items, "total": len(items),
            "horizon_days": horizon, "forecast_run": _run_public(run), "rules": RULES,
            "skipped_medicines_missing_stock_or_forecast": skipped,
            "caveats": ["Uses a MODEL-GENERATED forecast of SYNTHETIC data; forecasts compound error with horizon.",
                        "Compares forecast demand with CURRENT stock only; future receipts are not modelled.",
                        "No order quantity is prescribed; 'projected shortfall' is the plain arithmetic difference."],
            "meta": meta(as_of)}
