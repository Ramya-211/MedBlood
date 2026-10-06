"""
medicine_inventory_queries.py

Raw SQL for inventory (stock ledger: medicine_inventory) and batches/expiry (batch ledger:
medicine_batches). NOTE: the two ledgers are independent in the supplied data and do NOT
reconcile; they are always reported side by side, never summed together.

days_of_cover = closing_stock / (average of medicine_demand.units_issued over the 30 days
ending at the as-of date) -- the same quantity the supplied stock_status rule is based on.
"""


def latest_inventory_date(cur):
    cur.execute("SELECT MAX(inv_date) AS d FROM medicine_inventory")
    return cur.fetchone()["d"]


def _inv_filters(medicine_id, category, stock_status, search):
    clauses, params = [], []
    if medicine_id:
        clauses.append("i.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if stock_status:
        clauses.append("i.stock_status = %s"); params.append(stock_status)
    if search:
        clauses.append("(m.medicine_name LIKE %s OR i.medicine_id LIKE %s)"); params.extend([f"%{search}%", f"%{search}%"])
    return clauses, params


_COVER_JOIN = (
    "LEFT JOIN (SELECT d.medicine_id, AVG(d.units_issued) AS avg_daily_issued_30d FROM medicine_demand d "
    "WHERE d.demand_date > DATE_SUB(%s, INTERVAL 30 DAY) AND d.demand_date <= %s GROUP BY d.medicine_id) c "
    "ON c.medicine_id = i.medicine_id"
)


def current_inventory(cur, as_of, medicine_id, category, stock_status, search, order_sql, limit, offset):
    clauses, params = _inv_filters(medicine_id, category, stock_status, search)
    clauses.insert(0, "i.inv_date = %s")
    where = " WHERE " + " AND ".join(clauses)
    base = f"FROM medicine_inventory i JOIN medicines m ON m.medicine_id = i.medicine_id {_COVER_JOIN}{where}"
    all_params = (as_of, as_of, as_of, *params)
    cur.execute(f"SELECT COUNT(*) AS n {base}", all_params)
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT i.medicine_id, m.medicine_name, m.category, m.dosage_form, i.inv_date AS as_of_date, i.opening_stock, "
        f"i.units_received, i.units_issued, i.units_adjusted, i.closing_stock, i.stock_status, "
        f"c.avg_daily_issued_30d, i.closing_stock / NULLIF(c.avg_daily_issued_30d, 0) AS days_of_cover "
        f"{base} ORDER BY {order_sql} LIMIT %s OFFSET %s", (*all_params, limit, offset))
    return cur.fetchall(), total


def inventory_summary(cur, as_of, category, medicine_id=None):
    clauses, params = ["i.inv_date = %s"], [as_of]
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if medicine_id:
        clauses.append("i.medicine_id = %s"); params.append(medicine_id)
    cur.execute(
        "SELECT i.stock_status, COUNT(*) AS medicines, SUM(i.closing_stock) AS units "
        "FROM medicine_inventory i JOIN medicines m ON m.medicine_id = i.medicine_id "
        "WHERE " + " AND ".join(clauses) + " GROUP BY i.stock_status", tuple(params))
    return cur.fetchall()


def inventory_history(cur, medicine_id, category, date_from, date_to, limit, offset):
    clauses, params = [], []
    if medicine_id:
        clauses.append("i.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if date_from:
        clauses.append("i.inv_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("i.inv_date <= %s"); params.append(date_to)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    base = f"FROM medicine_inventory i JOIN medicines m ON m.medicine_id = i.medicine_id{where}"
    cur.execute(f"SELECT COUNT(*) AS n {base}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT i.inv_date AS date, i.medicine_id, m.medicine_name, i.opening_stock, i.units_received, i.units_issued, "
        f"i.units_adjusted, i.closing_stock, i.stock_status {base} ORDER BY i.inv_date DESC, i.medicine_id LIMIT %s OFFSET %s",
        (*params, limit, offset))
    return cur.fetchall(), total


def movement_totals(cur, medicine_id, category, date_from, date_to):
    """Per-medicine stock movement over a date range (used by the inventory report)."""
    clauses, params = [], []
    if medicine_id:
        clauses.append("i.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if date_from:
        clauses.append("i.inv_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("i.inv_date <= %s"); params.append(date_to)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT i.medicine_id, SUM(i.units_received) AS total_received, SUM(i.units_issued) AS total_issued, "
        f"SUM(i.units_adjusted) AS total_adjusted, COUNT(*) AS days FROM medicine_inventory i "
        f"JOIN medicines m ON m.medicine_id = i.medicine_id{where} GROUP BY i.medicine_id", tuple(params))
    return cur.fetchall()


def status_trend(cur, medicine_id, category, date_from, date_to):
    clauses, params = [], []
    if medicine_id:
        clauses.append("i.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if date_from:
        clauses.append("i.inv_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("i.inv_date <= %s"); params.append(date_to)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT CONCAT(YEAR(i.inv_date), '-', LPAD(MONTH(i.inv_date), 2, '0')) AS month, i.stock_status, COUNT(*) AS medicine_days "
        f"FROM medicine_inventory i JOIN medicines m ON m.medicine_id = i.medicine_id{where} "
        f"GROUP BY month, i.stock_status ORDER BY month, i.stock_status", tuple(params))
    return cur.fetchall()


# ------------------------------------------------------------------ batches / expiry
_BATCH_DERIVED = (
    "SELECT b.batch_id, b.batch_number, b.medicine_id, m.medicine_name, m.category, b.manufacturing_date, "
    "b.expiry_date, b.units_in_batch, b.units_remaining, b.expiry_status AS stored_expiry_status, "
    "DATEDIFF(b.expiry_date, %s) AS days_remaining, "
    "CASE WHEN b.expiry_date < %s THEN 'Expired' WHEN DATEDIFF(b.expiry_date, %s) <= %s THEN 'Near Expiry' "
    "ELSE 'Safe' END AS expiry_status "
    "FROM medicine_batches b JOIN medicines m ON m.medicine_id = b.medicine_id"
)


def _batch_filters(medicine_id, category, status, search, expiry_from, expiry_to, min_units):
    clauses, params = [], []
    if medicine_id:
        clauses.append("x.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("x.category = %s"); params.append(category)
    if status:
        clauses.append("x.expiry_status = %s"); params.append(status)
    if search:
        clauses.append("(x.medicine_name LIKE %s OR x.batch_id LIKE %s OR x.batch_number LIKE %s)")
        params.extend([f"%{search}%"] * 3)
    if expiry_from:
        clauses.append("x.expiry_date >= %s"); params.append(expiry_from)
    if expiry_to:
        clauses.append("x.expiry_date <= %s"); params.append(expiry_to)
    if min_units:
        clauses.append("x.units_remaining >= %s"); params.append(min_units)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def batches(cur, as_of, near_days, medicine_id, category, status, search, expiry_from, expiry_to, min_units,
            order_sql, limit, offset):
    where, params = _batch_filters(medicine_id, category, status, search, expiry_from, expiry_to, min_units)
    base_params = (as_of, as_of, as_of, near_days)
    cur.execute(f"SELECT COUNT(*) AS n FROM ({_BATCH_DERIVED}) x{where}", (*base_params, *params))
    total = cur.fetchone()["n"]
    cur.execute(f"SELECT x.* FROM ({_BATCH_DERIVED}) x{where} ORDER BY {order_sql} LIMIT %s OFFSET %s",
                (*base_params, *params, limit, offset))
    return cur.fetchall(), total


def batch_status_summary(cur, as_of, near_days, medicine_id, category):
    where, params = _batch_filters(medicine_id, category, None, None, None, None, None)
    cur.execute(
        f"SELECT x.expiry_status, COUNT(*) AS batches, COALESCE(SUM(x.units_remaining),0) AS units, "
        f"MIN(x.days_remaining) AS min_days_remaining, MAX(x.days_remaining) AS max_days_remaining "
        f"FROM ({_BATCH_DERIVED}) x{where} GROUP BY x.expiry_status", (as_of, as_of, as_of, near_days, *params))
    return cur.fetchall()


def batch_summary_by_medicine(cur, as_of, near_days, medicine_id, category):
    where, params = _batch_filters(medicine_id, category, None, None, None, None, None)
    cur.execute(
        f"SELECT x.medicine_id, x.medicine_name, "
        f"SUM(x.expiry_status = 'Expired') AS expired_batches, "
        f"COALESCE(SUM(CASE WHEN x.expiry_status = 'Expired' THEN x.units_remaining END), 0) AS expired_units, "
        f"SUM(x.expiry_status = 'Near Expiry') AS near_expiry_batches, "
        f"COALESCE(SUM(CASE WHEN x.expiry_status = 'Near Expiry' THEN x.units_remaining END), 0) AS near_expiry_units, "
        f"SUM(x.expiry_status = 'Safe') AS safe_batches, COALESCE(SUM(x.units_remaining), 0) AS batch_units_total "
        f"FROM ({_BATCH_DERIVED}) x{where} GROUP BY x.medicine_id, x.medicine_name ORDER BY x.medicine_id",
        (as_of, as_of, as_of, near_days, *params))
    return cur.fetchall()


def reconciliation(cur, as_of, medicine_id, category):
    clauses, params = ["i.inv_date = %s"], [as_of]
    if medicine_id:
        clauses.append("i.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    cur.execute(
        "SELECT i.medicine_id, m.medicine_name, i.closing_stock AS inventory_closing_stock, "
        "COALESCE(b.batch_units, 0) AS batch_units_remaining, COALESCE(b.batches, 0) AS batch_count "
        "FROM medicine_inventory i JOIN medicines m ON m.medicine_id = i.medicine_id "
        "LEFT JOIN (SELECT medicine_id, SUM(units_remaining) AS batch_units, COUNT(*) AS batches "
        "FROM medicine_batches GROUP BY medicine_id) b ON b.medicine_id = i.medicine_id "
        "WHERE " + " AND ".join(clauses) + " ORDER BY i.medicine_id", tuple(params))
    return cur.fetchall()
