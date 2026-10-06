"""
medicine_alert_service.py

Medicine alerts = the CURRENT-STATE alert snapshot supplied with the dataset (single date), enriched with the
real current values behind each alert (stock, batch, anomaly figures). No alert is generated here and no
historical alert dates are invented.
"""

from app.database.db import db_cursor
from app.database.queries import medicine_alert_queries as aq
from app.services.medicine_common import ALERT_VOCABULARY, as_of_date, meta, validate_entities
from app.utils.query_helpers import page, resolve_sort, validate_range

ALERT_SORT = {
    "severity": "FIELD(a.severity, 'Critical', 'Warning', 'Info')", "date": "a.alert_date", "type": "a.alert_type",
    "medicine": "m.medicine_name", "id": "a.alert_id",
}
STOCK_TYPES = {"Low Stock", "Critical Stock", "Potential Shortage", "Overstock"}
DEMAND_TYPES = {"Demand Spike", "Demand Drop", "Anomaly", "Increasing Demand"}


def _enrich(r):
    t = r["alert_type"]
    value = None
    if t == "Expired":
        value = {"expired_batches": int(r["expired_batches"] or 0), "expired_units": int(r["expired_units"] or 0)}
    elif t == "Near Expiry":
        value = {"near_expiry_batches": int(r["near_expiry_batches"] or 0), "near_expiry_units": int(r["near_expiry_units"] or 0)}
    elif t in STOCK_TYPES:
        value = {"closing_stock": r["closing_stock"], "stock_status": r["current_stock_status"]}
    elif t in DEMAND_TYPES and r["anomaly_score"] is not None:
        value = {"actual_demand": r["anomaly_actual_demand"], "expected_demand": r["anomaly_expected_demand"],
                 "anomaly_score": r["anomaly_score"], "anomaly_type": r["anomaly_type"]}
    return {
        "alert_id": r["alert_id"], "date": r["alert_date"], "medicine_id": r["medicine_id"],
        "medicine_name": r["medicine_name"], "category": r["category"], "alert_type": t, "severity": r["severity"],
        "reason": r["message"], "relevant_value": value,
        "current_status": {"stock_status": r["current_stock_status"], "closing_stock": r["closing_stock"]},
    }


def alerts(alert_type, severity, medicine_id, category, search, date_from, date_to, sort, order, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, ALERT_SORT, "severity") + ", a.alert_date DESC, a.alert_id"
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = aq.alerts(cur, as_of, alert_type, severity, medicine_id, category, search, d_from, d_to,
                                order_sql, limit, offset)
        summary = aq.alert_summary(cur, medicine_id, category)
        expiry_summary = aq.expiry_alert_summary(cur, medicine_id, category)
        snap = aq.snapshot_dates(cur)
    present = sorted({s["alert_type"] for s in summary} | {s["alert_type"] for s in expiry_summary})
    return page([_enrich(r) for r in rows], total, limit, offset,
                summary={"medicine_level": summary, "batch_expiry_level": expiry_summary},
                snapshot={"alert_date_range": [snap["alerts_min"], snap["alerts_max"]],
                          "note": ("Current-state snapshot supplied with the dataset (single date). It is not a "
                                   "history, so date filters can only ever match that date.")},
                vocabulary={"supported_types": ALERT_VOCABULARY, "types_present_in_data": present,
                            "types_without_records": [t for t in ALERT_VOCABULARY if t not in present]},
                meta=meta(as_of))
