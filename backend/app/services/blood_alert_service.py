"""blood_alert_service.py — mirrors medicine_alert_service.py."""

from app.database.db import db_cursor
from app.database.queries import blood_alert_queries as aq
from app.services.blood_common import ALERT_VOCABULARY, as_of_date, meta, validate_segment
from app.utils.query_helpers import page, resolve_sort, validate_range

ALERT_SORT = {"severity": "FIELD(a.severity, 'Critical', 'Warning', 'Info')", "date": "a.alert_date",
              "type": "a.alert_type", "id": "a.alert_id"}
STOCK_TYPES = {"Low Stock", "Critical Stock", "Potential Shortage", "Overstock"}


def _enrich(r):
    t = r["alert_type"]
    value = None
    if t == "Expired":
        value = {"expired_batches": int(r["expired_batches"] or 0), "expired_units": int(r["expired_units"] or 0)}
    elif t == "Near Expiry":
        value = {"near_expiry_batches": int(r["near_expiry_batches"] or 0), "near_expiry_units": int(r["near_expiry_units"] or 0)}
    elif t in STOCK_TYPES:
        value = {"closing_stock": r["closing_stock"]}
    return {"alert_id": r["alert_id"], "date": r["alert_date"], "blood_group": r["blood_group"], "rh_type": r["rh_type"],
            "blood_component": r["blood_component"], "alert_type": t, "severity": r["severity"], "reason": r["message"],
            "relevant_value": value, "current_status": {"closing_stock": r["closing_stock"]}}


def alerts(alert_type, severity, blood_group, rh_type, blood_component, date_from, date_to, sort, order, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, ALERT_SORT, "severity") + ", a.alert_date DESC, a.alert_id"
    as_of = as_of_date()
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = aq.alerts(cur, as_of, alert_type, severity, blood_group, rh_type, blood_component, d_from, d_to,
                                order_sql, limit, offset)
        summary = aq.alert_summary(cur, blood_group, rh_type, blood_component)
        snap = aq.snapshot_dates(cur)
    present = sorted({s["alert_type"] for s in summary})
    return page([_enrich(r) for r in rows], total, limit, offset, summary={"by_type_severity": summary},
                snapshot={"alert_date_range": [snap["alerts_min"], snap["alerts_max"]],
                          "note": "Current-state snapshot supplied with the dataset (single date); not a history."},
                vocabulary={"supported_types": ALERT_VOCABULARY, "types_present_in_data": present,
                            "types_without_records": [t for t in ALERT_VOCABULARY if t not in present]},
                meta=meta(as_of))
