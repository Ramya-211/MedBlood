"""
medicine_expiry_service.py

Expiry management (batch ledger). Deliberately independent from demand forecasting: expiry status and
days remaining come ONLY from real expiry_date values and the as-of date.
"""

from app.database.db import db_cursor
from app.database.queries import medicine_alert_queries as aq
from app.database.queries import medicine_inventory_queries as iq
from app.services import medicine_inventory_service as inv_service
from app.services.medicine_common import meta, near_expiry_days, resolve_as_of, validate_entities
from app.utils.query_helpers import page, resolve_sort, validate_range

EXPIRY_ALERT_SORT = {"days_to_expiry": "e.days_to_expiry", "date": "e.alert_date", "severity":
                     "FIELD(e.severity, 'Critical', 'Warning', 'Info')", "medicine": "m.medicine_name",
                     "units": "b.units_remaining", "expiry_date": "e.expiry_date"}


def expiry_list(status, medicine_id, category, search, expiry_from, expiry_to, min_units, as_of, near_days, sort,
                order, limit, offset):
    return inv_service.batches(status, medicine_id, category, search, expiry_from, expiry_to, min_units, as_of,
                               near_days, sort, order, limit, offset)


def expiry_summary(medicine_id, category, as_of, near_days):
    as_of_d = resolve_as_of(as_of)
    nd = near_expiry_days(near_days)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        status_rows = {r["expiry_status"]: r for r in iq.batch_status_summary(cur, as_of_d, nd, medicine_id, category)}
        by_medicine = iq.batch_summary_by_medicine(cur, as_of_d, nd, medicine_id, category)
        priority, _ = iq.batches(cur, as_of_d, nd, medicine_id, category, "Near Expiry", None, None, None, None,
                                 "x.days_remaining ASC, x.units_remaining DESC", 10, 0)
    counts = {s: {"batches": int(status_rows[s]["batches"]) if s in status_rows else 0,
                  "units": int(status_rows[s]["units"]) if s in status_rows else 0,
                  "min_days_remaining": status_rows[s]["min_days_remaining"] if s in status_rows else None,
                  "max_days_remaining": status_rows[s]["max_days_remaining"] if s in status_rows else None}
              for s in ("Expired", "Near Expiry", "Safe")}
    at_risk = sorted([m for m in by_medicine if m["expired_units"] or m["near_expiry_units"]],
                     key=lambda m: -(int(m["expired_units"]) + int(m["near_expiry_units"])))
    return {"as_of_date": as_of_d, "near_expiry_days": nd, "by_status": counts,
            "units_approaching_expiry": counts["Near Expiry"]["units"], "units_expired": counts["Expired"]["units"],
            "medicines_with_expired_or_near_expiry_stock": len(at_risk), "by_medicine": at_risk,
            "expiry_priority_batches": {"definition": "Near-expiry batches ordered by fewest days remaining, then most units.",
                                        "items": priority},
            "note": "Batch ledger only; independent of demand forecasts and of the stock ledger.",
            "meta": meta(as_of_d)}


def expiry_alerts(severity, medicine_id, category, search, date_from, date_to, max_days, sort, order, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, EXPIRY_ALERT_SORT, "days_to_expiry")
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = aq.expiry_alerts(cur, severity, medicine_id, category, search, d_from, d_to, max_days,
                                       order_sql, limit, offset)
        summary = aq.expiry_alert_summary(cur, medicine_id, category)
        snap = aq.snapshot_dates(cur)
    return page(rows, total, limit, offset, summary=summary,
                snapshot={"alert_date_range": [snap["expiry_alerts_min"], snap["expiry_alerts_max"]],
                          "note": "Current-state snapshot supplied with the dataset (single date); not a history."},
                meta=meta())
