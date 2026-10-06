"""
blood_recommendation_service.py

Mirrors medicine_recommendation_service.py:
1. SUPPLIED SNAPSHOT (`recommendations`): as shipped with the dataset (single date), enriched with
   the segment's current stock (looked up separately, never merged into the supplied numbers).
2. FORECAST-BASED (`forecast_based`): computed live from real stored values (current stock + latest
   model forecast) using the same documented rules R1-R5 as Medicine, adapted to blood segments.
"""

from app.config import get_settings
from app.database.db import db_cursor
from app.database.queries import blood_alert_queries as aq
from app.database.queries import blood_forecast_queries as fq
from app.services.blood_common import as_of_date, meta, validate_segment
from app.services.blood_service import FORECAST_TREND_THRESHOLD, _run_public
from app.utils.errors import BadRequestError
from app.utils.query_helpers import page, resolve_sort, validate_range

REC_SORT = {"severity": "FIELD(r.severity, 'Critical', 'Warning', 'Info')", "date": "r.rec_date",
            "type": "r.recommendation_type", "id": "r.recommendation_id"}

RULES = [
    {"rule_id": "R1", "type": "Potential Shortage", "condition": "forecast demand over next H days > current closing stock"},
    {"rule_id": "R2", "type": "Excess Stock", "condition": "days_of_cover > overstock threshold AND forecast demand over H days <= current stock"},
    {"rule_id": "R3", "type": "Demand Increasing", "condition": "mean forecast of last 7 horizon days > +5% vs first 7 days"},
    {"rule_id": "R4", "type": "Demand Decreasing", "condition": "mean forecast of last 7 horizon days < -5% vs first 7 days"},
    {"rule_id": "R5", "type": "Normal Monitoring", "condition": "none of R1-R4 applies"},
]


def recommendations(rec_type, severity, blood_group, rh_type, blood_component, date_from, date_to, sort, order,
                    limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, REC_SORT, "severity") + ", r.rec_date DESC, r.recommendation_id"
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = aq.recommendations(cur, as_of, rec_type, severity, blood_group, rh_type, blood_component,
                                         d_from, d_to, order_sql, limit, offset)
        summary = aq.recommendation_summary(cur, blood_group, rh_type, blood_component)
        snap = aq.snapshot_dates(cur)
    items = [{"recommendation_id": r["recommendation_id"], "date": r["rec_date"], "blood_group": r["blood_group"],
              "rh_type": r["rh_type"], "blood_component": r["blood_component"], "recommendation_type": r["recommendation_type"],
              "severity": r["severity"], "why": r["reason"], "current_stock_at_time_of_snapshot": r["current_stock"],
              "supplied_predicted_demand": r["supplied_predicted_demand"], "days_of_cover_at_snapshot": r["days_of_cover"],
              "current_stock_now": r["current_stock_now"], "source": "SUPPLIED_SNAPSHOT"} for r in rows]
    return page(items, total, limit, offset, summary=summary,
                snapshot={"recommendation_date_range": [snap["recs_min"], snap["recs_max"]],
                          "note": ("Current-state snapshot supplied with the dataset (single date); not a history. "
                                   "11 segments have a NULL supplied_predicted_demand (documented limitation, not "
                                   "fabricated). See /recommendations/forecast-based for model-forecast-driven ones.")},
                meta=meta(as_of))


def forecast_based(horizon_days, blood_group, rh_type, blood_component):
    as_of = as_of_date()
    horizon = horizon_days or get_settings().forecast_shortage_horizon_days
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        run = fq.latest_run(cur)
        if not run:
            return {"available": False, "items": [], "total": 0, "rules": RULES,
                    "message": "No model-generated forecast exists yet (run `python -m app.ml.blood_ml train`).",
                    "meta": meta(as_of)}
        if not 1 <= horizon <= run["horizon_days"]:
            raise BadRequestError(f"horizon_days must be between 1 and {run['horizon_days']}.")
        rows = aq.forecast_recommendation_inputs(cur, as_of, run["run_id"], horizon, blood_group, rh_type, blood_component)

    items, skipped = [], []
    for r in rows:
        seg = f"{r['blood_group']}{'+' if r['rh_type']=='Positive' else '-'} {r['blood_component']}"
        if r["closing_stock"] is None or r["forecast_total"] is None:
            skipped.append(seg)
            continue
        stock, fc = int(r["closing_stock"]), float(r["forecast_total"])
        cover = r["days_of_cover"]
        base = {"blood_group": r["blood_group"], "rh_type": r["rh_type"], "blood_component": r["blood_component"],
                "as_of_date": as_of, "forecast_run_id": run["run_id"], "horizon_days": horizon,
                "source": "MODEL_FORECAST_AND_CURRENT_STOCK"}
        inputs = {"current_stock": stock, "days_of_cover": round(float(cover), 2) if cover is not None else None,
                  f"forecast_demand_next_{horizon}_days": round(fc, 2), "forecast_avg_daily": round(fc / horizon, 2)}
        fired = []
        if fc > stock:
            shortfall = fc - stock
            fired.append({**base, "rule_id": "R1", "recommendation_type": "Potential Shortage",
                          "severity": "Critical" if (cover is not None and cover < 5) else "Warning",
                          "why": (f"Model-forecast demand over the next {horizon} days ({fc:.1f} units) exceeds current "
                                  f"stock ({stock} units for {seg}); projected shortfall {shortfall:.1f} units before "
                                  f"any new collection/receipts."),
                          "recommended_action": "Review replenishment", "inputs": {**inputs, "projected_shortfall": round(shortfall, 2)}})
        elif cover is not None and cover > 30:
            fired.append({**base, "rule_id": "R2", "recommendation_type": "Excess Stock", "severity": "Info",
                          "why": (f"Stock ({stock} units, {cover:.1f} days of cover) for {seg} exceeds the overstock "
                                  f"threshold and covers the model-forecast demand for the next {horizon} days "
                                  f"({fc:.1f} units) with {stock - fc:.1f} units to spare."),
                          "recommended_action": "Review excess inventory", "inputs": {**inputs, "stock_minus_forecast": round(stock - fc, 2)}})
        a7, b7 = r["avg_first_7"], r["avg_last_7"]
        if a7 and b7 is not None and float(a7) > 0:
            change = (float(b7) - float(a7)) / float(a7)
            trend_inputs = {**inputs, "forecast_avg_first_7_days": round(float(a7), 2),
                            "forecast_avg_last_7_days": round(float(b7), 2), "forecast_change_percent": round(change * 100, 2)}
            if change > FORECAST_TREND_THRESHOLD:
                fired.append({**base, "rule_id": "R3", "recommendation_type": "Demand Increasing", "severity": "Info",
                              "why": (f"Forecast demand for {seg} rises {change * 100:.1f}% between the first and last "
                                      f"7 days of the {run['horizon_days']}-day forecast ({float(a7):.1f} -> {float(b7):.1f} units/day)."),
                              "recommended_action": "Prepare for increased requirement", "inputs": trend_inputs})
            elif change < -FORECAST_TREND_THRESHOLD:
                fired.append({**base, "rule_id": "R4", "recommendation_type": "Demand Decreasing", "severity": "Info",
                              "why": (f"Forecast demand for {seg} falls {abs(change) * 100:.1f}% between the first and "
                                      f"last 7 days of the {run['horizon_days']}-day forecast ({float(a7):.1f} -> {float(b7):.1f} units/day)."),
                              "recommended_action": "Monitor for overstock risk", "inputs": trend_inputs})
        if not fired:
            fired.append({**base, "rule_id": "R5", "recommendation_type": "Normal Monitoring", "severity": "Info",
                          "why": (f"Current stock ({stock} units) for {seg} covers the model-forecast demand for the "
                                  f"next {horizon} days ({fc:.1f} units) and the forecast trend is within +/-5%."),
                          "recommended_action": "No action needed", "inputs": inputs})
        items.extend(fired)
    return {"available": True, "type": "FORECAST_BASED_RECOMMENDATIONS", "items": items, "total": len(items),
            "horizon_days": horizon, "forecast_run": _run_public(run), "rules": RULES,
            "skipped_segments_missing_stock_or_forecast": skipped,
            "caveats": ["Uses a MODEL-GENERATED forecast of SYNTHETIC data; forecasts compound error with horizon.",
                        "Compares forecast demand with CURRENT stock only; future collection/receipts are not modelled.",
                        "No order quantity is prescribed beyond the plain arithmetic shortfall."],
            "meta": meta(as_of)}
