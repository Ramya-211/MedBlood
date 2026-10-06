"""
blood_inventory_queries.py

Inventory (stock ledger: blood_inventory, FULL daily history 2021-01-01..2024-12-31, confirmed
during inspection -- NOT a snapshot) and batches/expiry (blood_batches, a snapshot of currently
active batches collected 2024-10-12..2024-12-31, confirmed during inspection).

DATASET NOTE: unlike medicine_inventory, blood_inventory has NO stored stock_status column, so
it is derived here from days_of_cover using the SAME documented thresholds used to build the
supplied blood_recommendations/blood_alerts data (Critical <2 days, Low <5 days, Overstock >30
days -- see backend/app data/blood_data/scripts/generate_recommendations_and_alerts.py).
expiry_status IS stored on blood_batches, but per Phase 6 instructions it is re-derived from
expiry_date here rather than trusted blindly; the stored value is also returned for comparison.
"""


def latest_inventory_date(cur):
    cur.execute("SELECT MAX(inv_date) AS d FROM blood_inventory")
    return cur.fetchone()["d"]


def _inv_filters(blood_group, rh_type, blood_component, stock_status):
    clauses, params = [], []
    if blood_group:
        clauses.append("x.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("x.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("x.blood_component = %s"); params.append(blood_component)
    if stock_status:
        clauses.append("x.stock_status = %s"); params.append(stock_status)
    return clauses, params


_STATUS_EXPR = (
    "CASE WHEN i.closing_stock / NULLIF(c.avg_daily_issued_30d, 0) < 2 THEN 'Critical' "
    "WHEN i.closing_stock / NULLIF(c.avg_daily_issued_30d, 0) < 5 THEN 'Low' "
    "WHEN i.closing_stock / NULLIF(c.avg_daily_issued_30d, 0) > 30 THEN 'Overstock' "
    "WHEN c.avg_daily_issued_30d IS NULL OR c.avg_daily_issued_30d = 0 THEN 'Normal' ELSE 'Normal' END"
)
_COVER_JOIN = (
    "LEFT JOIN (SELECT blood_group, rh_type, blood_component, AVG(units_issued) AS avg_daily_issued_30d "
    "FROM blood_demand WHERE demand_date > DATE_SUB(%s, INTERVAL 30 DAY) AND demand_date <= %s "
    "GROUP BY blood_group, rh_type, blood_component) c "
    "ON c.blood_group = i.blood_group AND c.rh_type = i.rh_type AND c.blood_component = i.blood_component"
)


def current_inventory(cur, as_of, blood_group, rh_type, blood_component, stock_status, order_sql, limit, offset):
    where_clauses, params = _inv_filters(blood_group, rh_type, blood_component, stock_status)
    where_clauses.insert(0, "i.inv_date = %s")
    inner = (f"SELECT i.blood_group, i.rh_type, i.blood_component, i.inv_date AS as_of_date, i.opening_stock, "
             f"i.units_received, i.units_issued, i.units_discarded, i.units_expired, i.closing_stock, "
             f"c.avg_daily_issued_30d, i.closing_stock / NULLIF(c.avg_daily_issued_30d, 0) AS days_of_cover, "
             f"{_STATUS_EXPR} AS stock_status FROM blood_inventory i {_COVER_JOIN} WHERE i.inv_date = %s")
    base_params = (as_of, as_of, as_of)
    outer_where = (" WHERE " + " AND ".join(where_clauses[1:])) if len(where_clauses) > 1 else ""
    cur.execute(f"SELECT COUNT(*) AS n FROM ({inner}) x{outer_where}", (*base_params, *params))
    total = cur.fetchone()["n"]
    cur.execute(f"SELECT x.* FROM ({inner}) x{outer_where} ORDER BY {order_sql} LIMIT %s OFFSET %s",
                (*base_params, *params, limit, offset))
    return cur.fetchall(), total


def inventory_summary(cur, as_of, blood_component=None):
    inner = (f"SELECT i.blood_group, i.rh_type, i.blood_component, i.closing_stock, "
             f"{_STATUS_EXPR} AS stock_status FROM blood_inventory i {_COVER_JOIN} WHERE i.inv_date = %s")
    params = [as_of, as_of, as_of]
    where = ""
    if blood_component:
        where = " WHERE x.blood_component = %s"; params.append(blood_component)
    cur.execute(f"SELECT x.stock_status, COUNT(*) AS segments, SUM(x.closing_stock) AS units "
                f"FROM ({inner}) x{where} GROUP BY x.stock_status", tuple(params))
    return cur.fetchall()


def inventory_history(cur, blood_group, rh_type, blood_component, date_from, date_to, limit, offset):
    clauses, params = [], []
    if blood_group:
        clauses.append("i.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("i.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("i.blood_component = %s"); params.append(blood_component)
    if date_from:
        clauses.append("i.inv_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("i.inv_date <= %s"); params.append(date_to)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(f"SELECT COUNT(*) AS n FROM blood_inventory i{where}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT i.inv_date AS date, i.blood_group, i.rh_type, i.blood_component, i.opening_stock, i.units_received, "
        f"i.units_issued, i.units_discarded, i.units_expired, i.closing_stock FROM blood_inventory i{where} "
        f"ORDER BY i.inv_date DESC, i.blood_group, i.rh_type, i.blood_component LIMIT %s OFFSET %s",
        (*params, limit, offset))
    return cur.fetchall(), total


# ------------------------------------------------------------------ batches / expiry
_BATCH_DERIVED = (
    "SELECT b.batch_id, b.blood_group, b.rh_type, b.blood_component, b.collection_date, b.expiry_date, "
    "b.units_in_batch, b.units_remaining, b.expiry_status AS stored_expiry_status, "
    "DATEDIFF(b.expiry_date, %s) AS days_remaining, "
    "CASE WHEN b.expiry_date < %s THEN 'Expired' WHEN DATEDIFF(b.expiry_date, %s) <= %s THEN 'Near Expiry' "
    "ELSE 'Safe' END AS expiry_status FROM blood_batches b"
)


def _batch_filters(blood_group, rh_type, blood_component, status, expiry_from, expiry_to, min_units):
    clauses, params = [], []
    if blood_group:
        clauses.append("x.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("x.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("x.blood_component = %s"); params.append(blood_component)
    if status:
        clauses.append("x.expiry_status = %s"); params.append(status)
    if expiry_from:
        clauses.append("x.expiry_date >= %s"); params.append(expiry_from)
    if expiry_to:
        clauses.append("x.expiry_date <= %s"); params.append(expiry_to)
    if min_units:
        clauses.append("x.units_remaining >= %s"); params.append(min_units)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def batches(cur, as_of, near_days, blood_group, rh_type, blood_component, status, expiry_from, expiry_to, min_units,
            order_sql, limit, offset):
    where, params = _batch_filters(blood_group, rh_type, blood_component, status, expiry_from, expiry_to, min_units)
    base_params = (as_of, as_of, as_of, near_days)
    cur.execute(f"SELECT COUNT(*) AS n FROM ({_BATCH_DERIVED}) x{where}", (*base_params, *params))
    total = cur.fetchone()["n"]
    cur.execute(f"SELECT x.* FROM ({_BATCH_DERIVED}) x{where} ORDER BY {order_sql} LIMIT %s OFFSET %s",
                (*base_params, *params, limit, offset))
    return cur.fetchall(), total


def batch_status_summary(cur, as_of, near_days, blood_group, rh_type, blood_component):
    where, params = _batch_filters(blood_group, rh_type, blood_component, None, None, None, None)
    cur.execute(
        f"SELECT x.expiry_status, COUNT(*) AS batches, COALESCE(SUM(x.units_remaining),0) AS units, "
        f"MIN(x.days_remaining) AS min_days_remaining, MAX(x.days_remaining) AS max_days_remaining "
        f"FROM ({_BATCH_DERIVED}) x{where} GROUP BY x.expiry_status", (as_of, as_of, as_of, near_days, *params))
    return cur.fetchall()


def batch_summary_by_segment(cur, as_of, near_days, blood_group, rh_type, blood_component):
    where, params = _batch_filters(blood_group, rh_type, blood_component, None, None, None, None)
    cur.execute(
        f"SELECT x.blood_group, x.rh_type, x.blood_component, "
        f"SUM(x.expiry_status = 'Expired') AS expired_batches, "
        f"COALESCE(SUM(CASE WHEN x.expiry_status = 'Expired' THEN x.units_remaining END), 0) AS expired_units, "
        f"SUM(x.expiry_status = 'Near Expiry') AS near_expiry_batches, "
        f"COALESCE(SUM(CASE WHEN x.expiry_status = 'Near Expiry' THEN x.units_remaining END), 0) AS near_expiry_units, "
        f"SUM(x.expiry_status = 'Safe') AS safe_batches, COALESCE(SUM(x.units_remaining), 0) AS batch_units_total "
        f"FROM ({_BATCH_DERIVED}) x{where} GROUP BY x.blood_group, x.rh_type, x.blood_component "
        f"ORDER BY x.blood_group, x.rh_type, x.blood_component", (as_of, as_of, as_of, near_days, *params))
    return cur.fetchall()


def stored_vs_derived_mismatches(cur, as_of, near_days):
    """Compares the supplied expiry_status column with the status derived here from expiry_date."""
    cur.execute(f"SELECT COUNT(*) AS n FROM ({_BATCH_DERIVED}) x WHERE x.expiry_status <> x.stored_expiry_status",
                (as_of, as_of, as_of, near_days))
    return cur.fetchone()["n"]


def reconciliation(cur, as_of, blood_group, rh_type, blood_component):
    clauses, params = ["i.inv_date = %s"], [as_of]
    if blood_group:
        clauses.append("i.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("i.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("i.blood_component = %s"); params.append(blood_component)
    cur.execute(
        "SELECT i.blood_group, i.rh_type, i.blood_component, i.closing_stock AS inventory_closing_stock, "
        "COALESCE(b.batch_units, 0) AS batch_units_remaining, COALESCE(b.batches, 0) AS batch_count "
        "FROM blood_inventory i LEFT JOIN (SELECT blood_group, rh_type, blood_component, SUM(units_remaining) AS batch_units, "
        "COUNT(*) AS batches FROM blood_batches GROUP BY blood_group, rh_type, blood_component) b "
        "ON b.blood_group = i.blood_group AND b.rh_type = i.rh_type AND b.blood_component = i.blood_component "
        "WHERE " + " AND ".join(clauses) + " ORDER BY i.blood_group, i.rh_type, i.blood_component", tuple(params))
    return cur.fetchall()
