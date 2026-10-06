"""blood_expiry_service.py — mirrors medicine_expiry_service.py. Independent from demand forecasting."""

from app.database.db import db_cursor
from app.database.queries import blood_inventory_queries as iq
from app.services import blood_inventory_service as inv_service
from app.services.blood_common import meta, near_expiry_days, resolve_as_of, validate_segment


def expiry_list(status, blood_group, rh_type, blood_component, expiry_from, expiry_to, min_units, as_of, near_days,
                sort, order, limit, offset):
    return inv_service.batches(status, blood_group, rh_type, blood_component, expiry_from, expiry_to, min_units,
                               as_of, near_days, sort, order, limit, offset)


def expiry_summary(blood_group, rh_type, blood_component, as_of, near_days):
    as_of_d = resolve_as_of(as_of)
    nd = near_expiry_days(near_days)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        status_rows = {r["expiry_status"]: r for r in iq.batch_status_summary(cur, as_of_d, nd, blood_group, rh_type, blood_component)}
        by_segment = iq.batch_summary_by_segment(cur, as_of_d, nd, blood_group, rh_type, blood_component)
        priority, _ = iq.batches(cur, as_of_d, nd, blood_group, rh_type, blood_component, "Near Expiry", None, None,
                                 None, "x.days_remaining ASC, x.units_remaining DESC", 10, 0)
    counts = {s: {"batches": int(status_rows[s]["batches"]) if s in status_rows else 0,
                  "units": int(status_rows[s]["units"]) if s in status_rows else 0,
                  "min_days_remaining": status_rows[s]["min_days_remaining"] if s in status_rows else None,
                  "max_days_remaining": status_rows[s]["max_days_remaining"] if s in status_rows else None}
              for s in ("Expired", "Near Expiry", "Safe")}
    at_risk = sorted([s for s in by_segment if s["expired_units"] or s["near_expiry_units"]],
                     key=lambda s: -(int(s["expired_units"]) + int(s["near_expiry_units"])))
    return {"as_of_date": as_of_d, "near_expiry_days": nd, "by_status": counts,
            "units_approaching_expiry": counts["Near Expiry"]["units"], "units_expired": counts["Expired"]["units"],
            "segments_with_expired_or_near_expiry_stock": len(at_risk), "by_segment": at_risk,
            "expiry_priority_batches": {"definition": "Near-expiry batches ordered by fewest days remaining, then most units.",
                                        "items": priority},
            "note": "Batch ledger only; independent of demand forecasts and of the daily stock ledger.",
            "meta": meta(as_of_d)}
