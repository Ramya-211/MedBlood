"""blood_inventory_service.py — mirrors medicine_inventory_service.py. Stock ledger is
blood_inventory (a full daily history, confirmed during inspection, not a snapshot)."""

from app.database.db import db_cursor
from app.database.queries import blood_inventory_queries as iq
from app.services.blood_common import STOCK_RULE, meta, near_expiry_days, resolve_as_of, validate_segment
from app.utils.query_helpers import page, resolve_sort, validate_range

INV_SORT = {"group": "i.blood_group", "stock": "x.closing_stock", "received": "x.units_received",
            "issued": "x.units_issued", "days_of_cover": "x.days_of_cover",
            "status": "FIELD(x.stock_status, 'Critical', 'Low', 'Normal', 'Overstock')"}
BATCH_SORT = {"days_remaining": "x.days_remaining", "expiry_date": "x.expiry_date", "units": "x.units_remaining",
              "batch_id": "x.batch_id", "collection_date": "x.collection_date",
              "status": "FIELD(x.expiry_status, 'Expired', 'Near Expiry', 'Safe')"}


def _round(r, keys, nd=2):
    for k in keys:
        if r.get(k) is not None:
            r[k] = round(float(r[k]), nd)


def inventory(stock_status, blood_group, rh_type, blood_component, as_of, sort, order, limit, offset):
    as_of_d = resolve_as_of(as_of)
    order_sql = resolve_sort(sort, order, INV_SORT, "group")
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = iq.current_inventory(cur, as_of_d, blood_group, rh_type, blood_component, stock_status,
                                           order_sql, limit, offset)
    for r in rows:
        _round(r, ("avg_daily_issued_30d", "days_of_cover"))
    return page(rows, total, limit, offset, as_of_date=as_of_d, stock_rule=STOCK_RULE,
                message=None if total else "No inventory rows match these filters on this date.", meta=meta(as_of_d))


def inventory_summary(as_of, blood_component):
    as_of_d = resolve_as_of(as_of)
    with db_cursor() as cur:
        rows = {r["stock_status"]: r for r in iq.inventory_summary(cur, as_of_d, blood_component)}
    by_status = {s: {"segments": int(rows[s]["segments"]) if s in rows else 0, "units": int(rows[s]["units"]) if s in rows else 0}
                for s in ("Critical", "Low", "Normal", "Overstock")}
    return {"as_of_date": as_of_d, "by_status": by_status,
            "total_segments": sum(v["segments"] for v in by_status.values()),
            "total_units": sum(v["units"] for v in by_status.values()),
            "attention_needed": {"low_or_critical": by_status["Low"]["segments"] + by_status["Critical"]["segments"],
                                 "overstock": by_status["Overstock"]["segments"]},
            "stock_rule": STOCK_RULE, "meta": meta(as_of_d)}


def inventory_history(blood_group, rh_type, blood_component, date_from, date_to, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = iq.inventory_history(cur, blood_group, rh_type, blood_component, d_from, d_to, limit, offset)
    return page(rows, total, limit, offset, meta=meta(),
                definition=("closing_stock = opening_stock + units_received - units_issued - units_discarded - "
                            "units_expired (verified at import). This is a FULL daily history, not a snapshot."))


def batches(status, blood_group, rh_type, blood_component, expiry_from, expiry_to, min_units, as_of, near_days,
            sort, order, limit, offset):
    as_of_d = resolve_as_of(as_of)
    nd = near_expiry_days(near_days)
    e_from, e_to = validate_range(expiry_from, expiry_to)
    order_sql = resolve_sort(sort, order, BATCH_SORT, "days_remaining")
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = iq.batches(cur, as_of_d, nd, blood_group, rh_type, blood_component, status, e_from, e_to,
                                 min_units, order_sql, limit, offset)
        mismatches = iq.stored_vs_derived_mismatches(cur, as_of_d, nd)
    return page(rows, total, limit, offset, as_of_date=as_of_d, near_expiry_days=nd,
                rule=(f"days_remaining = expiry_date - as-of date. Expired: days_remaining < 0; Near Expiry: "
                      f"0 <= days_remaining <= {nd}; otherwise Safe. Status is DERIVED here from expiry_date, not "
                      f"taken from the stored column (stored_expiry_status shown for comparison; "
                      f"{mismatches} row(s) differ from the derived status at this as-of date/window)."),
                meta=meta(as_of_d))


def reconciliation(blood_group, rh_type, blood_component, as_of):
    as_of_d = resolve_as_of(as_of)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = iq.reconciliation(cur, as_of_d, blood_group, rh_type, blood_component)
    for r in rows:
        r["difference_batch_minus_inventory"] = int(r["batch_units_remaining"]) - int(r["inventory_closing_stock"])
    return {"as_of_date": as_of_d, "items": rows, "total": len(rows),
            "totals": {"inventory_closing_stock": sum(int(r["inventory_closing_stock"]) for r in rows),
                       "batch_units_remaining": sum(int(r["batch_units_remaining"]) for r in rows)},
            "note": ("DATASET LIMITATION: blood_inventory (daily ledger) and blood_batches (batches active as of "
                     "the last ~80 days of the data) were generated independently and do not fully reconcile -- "
                     "blood_batches only covers recently-collected units, not the full inventory history. Shown "
                     "side by side and never merged."),
            "meta": meta(as_of_d)}
