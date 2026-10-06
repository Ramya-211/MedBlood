"""
medicine_inventory_service.py

Stock-ledger inventory (opening/received/issued/adjusted/closing, stock_status) and batch-wise views.
stock_status values are the supplied ones; days_of_cover is computed from real issuance values.
The stock ledger and the batch ledger are independent in the supplied data and never merged.
"""

from app.database.db import db_cursor
from app.database.queries import medicine_inventory_queries as iq
from app.services.medicine_common import (STOCK_RULE, meta, near_expiry_days, resolve_as_of, validate_entities)
from app.utils.query_helpers import page, resolve_sort, validate_range

INV_SORT = {
    "medicine": "m.medicine_name", "medicine_id": "i.medicine_id", "category": "m.category",
    "stock": "i.closing_stock", "received": "i.units_received", "issued": "i.units_issued",
    "days_of_cover": "days_of_cover",
    "status": "FIELD(i.stock_status, 'Critical', 'Low', 'Normal', 'Overstock')",
}
BATCH_SORT = {
    "days_remaining": "x.days_remaining", "expiry_date": "x.expiry_date", "units": "x.units_remaining",
    "medicine": "x.medicine_name", "batch_id": "x.batch_id", "manufacturing_date": "x.manufacturing_date",
    "status": "FIELD(x.expiry_status, 'Expired', 'Near Expiry', 'Safe')",
}


def _round(r, keys, nd=2):
    for k in keys:
        if r.get(k) is not None:
            r[k] = round(float(r[k]), nd)


def inventory(stock_status, medicine_id, category, search, as_of, sort, order, limit, offset):
    as_of_d = resolve_as_of(as_of)
    order_sql = resolve_sort(sort, order, INV_SORT, "medicine_id")
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = iq.current_inventory(cur, as_of_d, medicine_id, category, stock_status, search, order_sql, limit, offset)
    for r in rows:
        _round(r, ("avg_daily_issued_30d", "days_of_cover"))
    return page(rows, total, limit, offset, as_of_date=as_of_d, stock_rule=STOCK_RULE,
                message=None if total else "No inventory rows match these filters on this date.",
                meta=meta(as_of_d))


def inventory_summary(as_of, category):
    as_of_d = resolve_as_of(as_of)
    with db_cursor() as cur:
        validate_entities(cur, None, category)
        rows = {r["stock_status"]: r for r in iq.inventory_summary(cur, as_of_d, category)}
    by_status = {s: {"medicines": int(rows[s]["medicines"]) if s in rows else 0,
                     "units": int(rows[s]["units"]) if s in rows else 0}
                 for s in ("Critical", "Low", "Normal", "Overstock")}
    return {"as_of_date": as_of_d, "by_status": by_status,
            "total_medicines": sum(v["medicines"] for v in by_status.values()),
            "total_units": sum(v["units"] for v in by_status.values()),
            "attention_needed": {"low_or_critical": by_status["Low"]["medicines"] + by_status["Critical"]["medicines"],
                                 "overstock": by_status["Overstock"]["medicines"]},
            "stock_rule": STOCK_RULE, "meta": meta(as_of_d)}


def inventory_history(medicine_id, category, date_from, date_to, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = iq.inventory_history(cur, medicine_id, category, d_from, d_to, limit, offset)
    return page(rows, total, limit, offset, meta=meta(),
                definition="closing_stock = opening_stock + units_received - units_issued + units_adjusted (verified at import).")


def status_trend(medicine_id, category, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = iq.status_trend(cur, medicine_id, category, d_from, d_to)
    return {"items": rows, "total": len(rows),
            "definition": "Number of medicine-days in each stock_status per month (history of statuses, not a current alert).",
            "meta": meta()}


def batches(status, medicine_id, category, search, expiry_from, expiry_to, min_units, as_of, near_days, sort, order,
            limit, offset):
    as_of_d = resolve_as_of(as_of)
    nd = near_expiry_days(near_days)
    e_from, e_to = validate_range(expiry_from, expiry_to)
    order_sql = resolve_sort(sort, order, BATCH_SORT, "days_remaining")
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = iq.batches(cur, as_of_d, nd, medicine_id, category, status, search, e_from, e_to, min_units,
                                 order_sql, limit, offset)
    return page(rows, total, limit, offset, as_of_date=as_of_d, near_expiry_days=nd,
                rule=(f"days_remaining = expiry_date - as-of date. Expired: days_remaining < 0; Near Expiry: "
                      f"0 <= days_remaining <= {nd}; otherwise Safe. stored_expiry_status is the value supplied with "
                      f"the dataset (as-of 2024-12-31, 30-day window)."),
                meta=meta(as_of_d))


def reconciliation(medicine_id, category, as_of):
    as_of_d = resolve_as_of(as_of)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = iq.reconciliation(cur, as_of_d, medicine_id, category)
    for r in rows:
        r["difference_batch_minus_inventory"] = int(r["batch_units_remaining"]) - int(r["inventory_closing_stock"])
    return {"as_of_date": as_of_d, "items": rows, "total": len(rows),
            "totals": {"inventory_closing_stock": sum(int(r["inventory_closing_stock"]) for r in rows),
                       "batch_units_remaining": sum(int(r["batch_units_remaining"]) for r in rows)},
            "note": ("DATASET LIMITATION: the stock ledger (medicine_inventory) and the batch ledger (medicine_batches) "
                     "were generated independently and do not reconcile. They are shown side by side and never merged. "
                     "Stock status uses the stock ledger; expiry uses the batch ledger."),
            "meta": meta(as_of_d)}
