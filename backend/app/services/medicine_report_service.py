"""
medicine_report_service.py

Dedicated Medicine reports (distinct from the dashboard): Demand, Forecast, Inventory, Expiry,
Alert and Recommendation reports. Each returns summary statistics + a full table, exportable as CSV.
"""

from app.database.db import db_cursor
from app.database.queries import medicine_alert_queries as aq
from app.database.queries import medicine_demand_queries as dq
from app.database.queries import medicine_forecast_queries as fq
from app.database.queries import medicine_inventory_queries as iq
from app.services import medicine_service as ms
from app.services.medicine_common import as_of_date, meta, near_expiry_days, validate_entities
from app.utils.query_helpers import rows_to_csv, validate_range

REPORT_COLUMNS = {
    "demand": ["medicine_id", "medicine_name", "category", "total_requested", "total_issued", "total_dispensed",
               "avg_daily_requested", "peak_daily_requested", "days"],
    "forecast": ["medicine_id", "medicine_name", "category", "n", "mae", "rmse", "r2", "bias", "total_actual", "total_predicted"],
    "inventory": ["medicine_id", "opening_stock", "units_received", "units_issued", "units_adjusted", "closing_stock", "stock_status"],
    "expiry": ["batch_id", "medicine_id", "medicine_name", "manufacturing_date", "expiry_date", "days_remaining",
               "units_remaining", "expiry_status"],
    "alerts": ["alert_source", "alert_id", "alert_date", "medicine_id", "medicine_name", "alert_type", "severity",
               "message", "batch_id", "days_to_expiry"],
    "recommendations": ["recommendation_id", "rec_date", "medicine_id", "medicine_name", "category",
                        "recommendation_type", "severity", "reason", "recommended_action"],
}


def demand_report(medicine_id, category, date_from, date_to, search):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = dq.demand_by_medicine(cur, medicine_id, category, d_from, d_to, search, "total_requested DESC")
        kpi, _ = dq.demand_kpis(cur, medicine_id, category, d_from, d_to)
    return {"report": "demand", "filters": {"medicine_id": medicine_id, "category": category, "date_from": d_from, "date_to": d_to},
            "summary": {"total_requested": int(kpi["total_requested"]), "total_issued": int(kpi["total_issued"]),
                       "total_dispensed": int(kpi["total_dispensed"]), "medicines": kpi["medicines"],
                       "date_range": [kpi["first_date"], kpi["last_date"]]},
            "rows": rows, "row_count": len(rows), "columns": REPORT_COLUMNS["demand"], "meta": meta()}


def forecast_report(medicine_id, category, date_from, date_to):
    o_from, o_to = (validate_range(date_from, date_to)[0], validate_range(date_from, date_to)[1])
    from datetime import timedelta
    o_from = o_from - timedelta(days=1) if o_from else None
    o_to = o_to - timedelta(days=1) if o_to else None
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = fq.backtest_by_medicine(cur, medicine_id, category, o_from, o_to)
        overall = fq.backtest_overall(cur, medicine_id, category, o_from, o_to)
        comp = fq.model_comparison(cur)
        run = fq.latest_run(cur)
    return {"report": "forecast", "filters": {"medicine_id": medicine_id, "category": category, "date_from": date_from, "date_to": date_to},
            "summary": {"backtest_overall": ms._metrics_public(overall), "model_comparison": comp,
                       "active_forecast_run": ms._run_public(run) if run else None},
            "rows": [dict(r, **ms._metrics_public(r)) for r in rows], "row_count": len(rows),
            "columns": REPORT_COLUMNS["forecast"], "meta": meta()}


def inventory_report(medicine_id, category, as_of):
    from app.services.medicine_common import resolve_as_of
    as_of_d = resolve_as_of(as_of)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, _ = iq.current_inventory(cur, as_of_d, medicine_id, category, None, None, "i.medicine_id", 10000, 0)
        summary = {r["stock_status"]: r for r in iq.inventory_summary(cur, as_of_d, category)}
    return {"report": "inventory", "as_of_date": as_of_d, "filters": {"medicine_id": medicine_id, "category": category},
            "summary": {s: {"medicines": int(summary[s]["medicines"]) if s in summary else 0,
                            "units": int(summary[s]["units"]) if s in summary else 0}
                       for s in ("Critical", "Low", "Normal", "Overstock")},
            "rows": rows, "row_count": len(rows), "columns": REPORT_COLUMNS["inventory"], "meta": meta(as_of_d)}


def expiry_report(medicine_id, category, as_of, near_days):
    from app.services.medicine_common import resolve_as_of
    as_of_d = resolve_as_of(as_of)
    nd = near_expiry_days(near_days)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, _ = iq.batches(cur, as_of_d, nd, medicine_id, category, None, None, None, None, None,
                             "x.days_remaining ASC", 10000, 0)
        summary = iq.batch_status_summary(cur, as_of_d, nd, medicine_id, category)
    return {"report": "expiry", "as_of_date": as_of_d, "near_expiry_days": nd,
            "filters": {"medicine_id": medicine_id, "category": category},
            "summary": {r["expiry_status"]: {"batches": int(r["batches"]), "units": int(r["units"])} for r in summary},
            "rows": rows, "row_count": len(rows), "columns": REPORT_COLUMNS["expiry"], "meta": meta(as_of_d)}


def alert_report(medicine_id, category, date_from, date_to, alert_type, severity):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, _ = aq.combined_alerts(cur, alert_type, severity, medicine_id, category, None, d_from, d_to,
                                     "alert_date DESC", 10000, 0)
    by_type = {}
    for r in rows:
        by_type[r["alert_type"]] = by_type.get(r["alert_type"], 0) + 1
    return {"report": "alerts", "filters": {"medicine_id": medicine_id, "category": category, "date_from": d_from,
                                            "date_to": d_to, "alert_type": alert_type, "severity": severity},
            "summary": {"total": len(rows), "by_type": by_type}, "rows": rows, "row_count": len(rows),
            "columns": REPORT_COLUMNS["alerts"], "meta": meta()}


def recommendation_report(medicine_id, category, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, _ = aq.recommendations(cur, as_of, None, None, medicine_id, category, None, d_from, d_to,
                                     "r.rec_date DESC", 10000, 0)
        summary = aq.recommendation_summary(cur, medicine_id, category)
    return {"report": "recommendations", "filters": {"medicine_id": medicine_id, "category": category,
                                                      "date_from": d_from, "date_to": d_to},
            "summary": summary, "rows": rows, "row_count": len(rows),
            "columns": REPORT_COLUMNS["recommendations"], "meta": meta(as_of)}


REPORT_FUNCS = {
    "demand": demand_report, "forecast": forecast_report, "inventory": inventory_report,
    "expiry": expiry_report, "alerts": alert_report, "recommendations": recommendation_report,
}


def as_csv(report_type: str, rows: list) -> str:
    return rows_to_csv(rows, REPORT_COLUMNS[report_type])
