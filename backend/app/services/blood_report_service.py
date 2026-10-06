"""blood_report_service.py — mirrors medicine_report_service.py, plus a Supply-vs-Demand report
(a Blood-specific addition per the project requirements)."""

from datetime import timedelta

from app.database.db import db_cursor
from app.database.queries import blood_alert_queries as aq
from app.database.queries import blood_demand_queries as dq
from app.database.queries import blood_forecast_queries as fq
from app.database.queries import blood_inventory_queries as iq
from app.database.queries import blood_supply_queries as sq
from app.services import blood_service as bs
from app.services.blood_common import as_of_date, meta, near_expiry_days, resolve_as_of, validate_segment
from app.utils.query_helpers import rows_to_csv, validate_range

REPORT_COLUMNS = {
    "demand": ["blood_group", "rh_type", "blood_component", "total_requested", "total_issued", "total_transfused",
               "avg_daily_requested", "peak_daily_requested", "days"],
    "forecast": ["blood_group", "rh_type", "blood_component", "n", "mae", "rmse", "r2", "bias", "total_actual", "total_predicted"],
    "inventory": ["blood_group", "rh_type", "blood_component", "opening_stock", "units_received", "units_issued",
                  "units_discarded", "units_expired", "closing_stock", "stock_status"],
    "expiry": ["batch_id", "blood_group", "rh_type", "blood_component", "collection_date", "expiry_date",
               "days_remaining", "units_remaining", "expiry_status"],
    "alerts": ["alert_id", "alert_date", "blood_group", "rh_type", "blood_component", "alert_type", "severity", "message"],
    "recommendations": ["recommendation_id", "rec_date", "blood_group", "rh_type", "blood_component",
                        "recommendation_type", "severity", "reason"],
    "supply_vs_demand": ["blood_type", "total_demand_requested", "total_supply_donation_volume",
                         "current_available_inventory", "supply_minus_demand"],
}


def demand_report(blood_group, rh_type, blood_component, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = dq.demand_by_segment(cur, blood_group, rh_type, blood_component, d_from, d_to, "total_requested DESC")
        kpi, _ = dq.demand_kpis(cur, blood_group, rh_type, blood_component, d_from, d_to)
    return {"report": "demand", "filters": {"blood_group": blood_group, "rh_type": rh_type, "blood_component": blood_component,
                                            "date_from": d_from, "date_to": d_to},
            "summary": {"total_requested": int(kpi["total_requested"]), "total_issued": int(kpi["total_issued"]),
                       "total_transfused": int(kpi["total_transfused"]), "segments": kpi["segments"],
                       "date_range": [kpi["first_date"], kpi["last_date"]]},
            "rows": rows, "row_count": len(rows), "columns": REPORT_COLUMNS["demand"], "meta": meta()}


def forecast_report(blood_group, rh_type, blood_component, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    o_from = d_from - timedelta(days=1) if d_from else None
    o_to = d_to - timedelta(days=1) if d_to else None
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = fq.backtest_by_segment(cur, blood_group, rh_type, blood_component, o_from, o_to)
        overall = fq.backtest_overall(cur, blood_group, rh_type, blood_component, o_from, o_to)
        comp = fq.model_comparison(cur)
        run = fq.latest_run(cur)
    return {"report": "forecast", "filters": {"blood_group": blood_group, "rh_type": rh_type, "blood_component": blood_component,
                                              "date_from": date_from, "date_to": date_to},
            "summary": {"backtest_overall": bs._metrics_public(overall), "model_comparison": comp,
                       "active_forecast_run": bs._run_public(run) if run else None},
            "rows": [dict(r, **bs._metrics_public(r)) for r in rows], "row_count": len(rows),
            "columns": REPORT_COLUMNS["forecast"], "meta": meta()}


def inventory_report(blood_group, rh_type, blood_component, as_of):
    as_of_d = resolve_as_of(as_of)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, _ = iq.current_inventory(cur, as_of_d, blood_group, rh_type, blood_component, None, "i.blood_group", 10000, 0)
        summary = {r["stock_status"]: r for r in iq.inventory_summary(cur, as_of_d, blood_component)}
    return {"report": "inventory", "as_of_date": as_of_d, "filters": {"blood_group": blood_group, "rh_type": rh_type,
                                                                      "blood_component": blood_component},
            "summary": {s: {"segments": int(summary[s]["segments"]) if s in summary else 0,
                            "units": int(summary[s]["units"]) if s in summary else 0}
                       for s in ("Critical", "Low", "Normal", "Overstock")},
            "rows": rows, "row_count": len(rows), "columns": REPORT_COLUMNS["inventory"], "meta": meta(as_of_d)}


def expiry_report(blood_group, rh_type, blood_component, as_of, near_days):
    as_of_d = resolve_as_of(as_of)
    nd = near_expiry_days(near_days)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, _ = iq.batches(cur, as_of_d, nd, blood_group, rh_type, blood_component, None, None, None, None,
                             "x.days_remaining ASC", 10000, 0)
        summary = iq.batch_status_summary(cur, as_of_d, nd, blood_group, rh_type, blood_component)
    return {"report": "expiry", "as_of_date": as_of_d, "near_expiry_days": nd,
            "filters": {"blood_group": blood_group, "rh_type": rh_type, "blood_component": blood_component},
            "summary": {r["expiry_status"]: {"batches": int(r["batches"]), "units": int(r["units"])} for r in summary},
            "rows": rows, "row_count": len(rows), "columns": REPORT_COLUMNS["expiry"], "meta": meta(as_of_d)}


def alert_report(blood_group, rh_type, blood_component, date_from, date_to, alert_type, severity):
    d_from, d_to = validate_range(date_from, date_to)
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, _ = aq.alerts(cur, as_of, alert_type, severity, blood_group, rh_type, blood_component, d_from, d_to,
                            "a.alert_date DESC", 10000, 0)
    by_type = {}
    for r in rows:
        by_type[r["alert_type"]] = by_type.get(r["alert_type"], 0) + 1
    return {"report": "alerts", "filters": {"blood_group": blood_group, "rh_type": rh_type, "blood_component": blood_component,
                                            "date_from": d_from, "date_to": d_to, "alert_type": alert_type, "severity": severity},
            "summary": {"total": len(rows), "by_type": by_type}, "rows": rows, "row_count": len(rows),
            "columns": REPORT_COLUMNS["alerts"], "meta": meta(as_of)}


def recommendation_report(blood_group, rh_type, blood_component, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, _ = aq.recommendations(cur, as_of, None, None, blood_group, rh_type, blood_component, d_from, d_to,
                                     "r.rec_date DESC", 10000, 0)
        summary = aq.recommendation_summary(cur, blood_group, rh_type, blood_component)
    return {"report": "recommendations", "filters": {"blood_group": blood_group, "rh_type": rh_type,
                                                      "blood_component": blood_component, "date_from": d_from, "date_to": d_to},
            "summary": summary, "rows": rows, "row_count": len(rows),
            "columns": REPORT_COLUMNS["recommendations"], "meta": meta(as_of)}


def supply_vs_demand_report(date_from, date_to):
    result = bs.supply_vs_demand(date_from, date_to)
    return {"report": "supply_vs_demand", "as_of_date": result["as_of_date"],
            "filters": {"date_from": date_from, "date_to": date_to}, "summary": {"definitions": result["definitions"],
                                                                                  "limitation": result["limitation"]},
            "rows": result["items"], "row_count": result["total"], "columns": REPORT_COLUMNS["supply_vs_demand"],
            "meta": result["meta"]}


REPORT_FUNCS = {
    "demand": demand_report, "forecast": forecast_report, "inventory": inventory_report, "expiry": expiry_report,
    "alerts": alert_report, "recommendations": recommendation_report, "supply_vs_demand": supply_vs_demand_report,
}


def as_csv(report_type: str, rows: list) -> str:
    return rows_to_csv(rows, REPORT_COLUMNS[report_type])
