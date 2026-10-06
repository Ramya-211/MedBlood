"""
medicine_demand_queries.py

Raw, parameterized SQL for medicine demand analysis (tables: medicines, medicine_demand,
medicine_demand_features-derived tables: medicine_trend_analysis, medicine_seasonality,
medicine_demand_anomalies, medicine_volume_tiers).

Rules: only fixed SQL fragments are concatenated (bucket expressions, sort clauses resolved
from allow-lists); every user-supplied value is a bound %s parameter.
"""

BUCKETS = {
    "daily": "d.demand_date",
    "weekly": "DATE_SUB(d.demand_date, INTERVAL WEEKDAY(d.demand_date) DAY)",           # Monday start
    "monthly": "DATE_SUB(d.demand_date, INTERVAL DAYOFMONTH(d.demand_date) - 1 DAY)",
    "yearly": "MAKEDATE(YEAR(d.demand_date), 1)",
}


def demand_where(medicine_id=None, category=None, date_from=None, date_to=None, with_dates=True):
    clauses, params = [], []
    if medicine_id:
        clauses.append("d.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("d.category = %s"); params.append(category)
    if with_dates and date_from:
        clauses.append("d.demand_date >= %s"); params.append(date_from)
    if with_dates and date_to:
        clauses.append("d.demand_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


# ------------------------------------------------------------------ catalogue / filters
def list_medicines(cur):
    cur.execute("SELECT medicine_id, medicine_name, category, dosage_form, manufacturer, pack_size, provenance "
                "FROM medicines ORDER BY medicine_id")
    return cur.fetchall()


def get_medicine(cur, medicine_id):
    cur.execute("SELECT medicine_id, medicine_name, category FROM medicines WHERE medicine_id = %s", (medicine_id,))
    return cur.fetchone()


def category_exists(cur, category):
    cur.execute("SELECT 1 AS x FROM medicines WHERE category = %s LIMIT 1", (category,))
    return cur.fetchone() is not None


def demand_date_bounds(cur):
    cur.execute("SELECT MIN(demand_date) AS min_date, MAX(demand_date) AS max_date FROM medicine_demand")
    return cur.fetchone()


def latest_inventory_date(cur):
    cur.execute("SELECT MAX(inv_date) AS d FROM medicine_inventory")
    return cur.fetchone()["d"]


# ------------------------------------------------------------------ demand series
def demand_series(cur, granularity, medicine_id, category, date_from, date_to, by_medicine, limit, offset):
    bucket = BUCKETS[granularity]
    where, params = demand_where(medicine_id, category, date_from, date_to)
    if by_medicine:
        extra, join = ", d.medicine_id, m.medicine_name", " JOIN medicines m ON m.medicine_id = d.medicine_id"
        group, order = "period_start, d.medicine_id, m.medicine_name", "period_start, d.medicine_id"
        inner_group = "period_start, d.medicine_id"
    else:
        extra, join, group, order, inner_group = "", "", "period_start", "period_start", "period_start"
    cur.execute(
        f"SELECT COUNT(*) AS n FROM (SELECT {bucket} AS period_start FROM medicine_demand d{where} "
        f"GROUP BY {inner_group}) t", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT {bucket} AS period_start{extra}, SUM(d.units_requested) AS units_requested, "
        f"SUM(d.units_issued) AS units_issued, SUM(d.units_dispensed) AS units_dispensed, "
        f"COUNT(DISTINCT d.demand_date) AS days_covered "
        f"FROM medicine_demand d{join}{where} GROUP BY {group} ORDER BY {order} LIMIT %s OFFSET %s",
        (*params, limit, offset))
    return cur.fetchall(), total


def demand_kpis(cur, medicine_id, category, date_from, date_to):
    where, params = demand_where(medicine_id, category, date_from, date_to)
    cur.execute(
        f"SELECT COALESCE(SUM(d.units_requested),0) AS total_requested, COALESCE(SUM(d.units_issued),0) AS total_issued, "
        f"COALESCE(SUM(d.units_dispensed),0) AS total_dispensed, COUNT(DISTINCT d.demand_date) AS days, "
        f"COUNT(DISTINCT d.medicine_id) AS medicines, MIN(d.demand_date) AS first_date, MAX(d.demand_date) AS last_date "
        f"FROM medicine_demand d{where}", tuple(params))
    kpi = cur.fetchone()
    days = {}
    for label, direction in (("peak_day", "DESC"), ("lowest_day", "ASC")):
        cur.execute(
            f"SELECT d.demand_date AS date, SUM(d.units_requested) AS units_requested FROM medicine_demand d{where} "
            f"GROUP BY d.demand_date ORDER BY units_requested {direction}, d.demand_date LIMIT 1", tuple(params))
        days[label] = cur.fetchone()
    return kpi, days


def rankings(cur, medicine_id, category, date_from, date_to):
    where, params = demand_where(medicine_id, category, date_from, date_to)
    cur.execute(
        f"SELECT d.medicine_id, m.medicine_name, d.category, SUM(d.units_requested) AS total_requested, "
        f"AVG(d.units_requested) AS avg_daily_requested FROM medicine_demand d "
        f"JOIN medicines m ON m.medicine_id = d.medicine_id{where} "
        f"GROUP BY d.medicine_id, m.medicine_name, d.category ORDER BY total_requested DESC, d.medicine_id", tuple(params))
    return cur.fetchall()


def variability(cur, medicine_id, category, date_from, date_to):
    where, params = demand_where(medicine_id, category, date_from, date_to)
    cur.execute(
        f"SELECT d.medicine_id, m.medicine_name, d.category, COUNT(*) AS days, AVG(d.units_requested) AS mean_daily, "
        f"STDDEV_SAMP(d.units_requested) AS std_daily, MIN(d.units_requested) AS min_daily, "
        f"MAX(d.units_requested) AS max_daily, "
        f"STDDEV_SAMP(d.units_requested) / NULLIF(AVG(d.units_requested), 0) AS coefficient_of_variation "
        f"FROM medicine_demand d JOIN medicines m ON m.medicine_id = d.medicine_id{where} "
        f"GROUP BY d.medicine_id, m.medicine_name, d.category ORDER BY coefficient_of_variation DESC", tuple(params))
    return cur.fetchall()


def moving_average(cur, window, medicine_id, category, date_from, date_to):
    """window is validated against an allow-list by the service, then cast to int (SQL frame bounds are literals).
    The window is computed over the FULL series first; the date filter is applied afterwards so early rows of a
    filtered range still see their true look-back."""
    n_prev = int(window) - 1
    inner_where, params = demand_where(medicine_id, category, None, None, with_dates=False)
    outer, outer_params = [], []
    if date_from:
        outer.append("x.demand_date >= %s"); outer_params.append(date_from)
    if date_to:
        outer.append("x.demand_date <= %s"); outer_params.append(date_to)
    outer_where = (" WHERE " + " AND ".join(outer)) if outer else ""
    cur.execute(
        f"SELECT * FROM (SELECT t.demand_date, t.total_requested, AVG(t.total_requested) OVER w AS moving_average, "
        f"COUNT(*) OVER w AS points_in_window FROM (SELECT d.demand_date, SUM(d.units_requested) AS total_requested "
        f"FROM medicine_demand d{inner_where} GROUP BY d.demand_date) t "
        f"WINDOW w AS (ORDER BY t.demand_date ROWS BETWEEN {n_prev} PRECEDING AND CURRENT ROW)) x{outer_where} "
        f"ORDER BY x.demand_date", tuple(params + outer_params))
    return cur.fetchall()


# ------------------------------------------------------------------ supplied analytics tables
def _catalog_where(alias, medicine_id, category, search=None):
    clauses, params = [], []
    if medicine_id:
        clauses.append(f"{alias}.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if search:
        clauses.append("m.medicine_name LIKE %s"); params.append(f"%{search}%")
    return clauses, params


def trends(cur, direction, medicine_id, category, search, order_sql):
    clauses, params = _catalog_where("t", medicine_id, category, search)
    if direction:
        clauses.append("t.trend_direction = %s"); params.append(direction)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT t.medicine_id, m.medicine_name, m.category, t.trend_slope, t.trend_direction, t.growth_rate_7d, "
        f"t.growth_rate_30d FROM medicine_trend_analysis t JOIN medicines m ON m.medicine_id = t.medicine_id"
        f"{where} ORDER BY {order_sql}", tuple(params))
    return cur.fetchall()


def seasonality(cur, medicine_id, category):
    clauses, params = _catalog_where("s", medicine_id, category)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT s.medicine_id, m.medicine_name, m.category, s.month_num AS month, s.season, s.seasonality_index "
        f"FROM medicine_seasonality s JOIN medicines m ON m.medicine_id = s.medicine_id{where} "
        f"ORDER BY s.medicine_id, s.month_num", tuple(params))
    return cur.fetchall()


def _anomaly_where(medicine_id, category, anomaly_type, date_from, date_to):
    clauses, params = _catalog_where("a", medicine_id, category)
    if anomaly_type:
        clauses.append("a.anomaly_type = %s"); params.append(anomaly_type)
    if date_from:
        clauses.append("a.anomaly_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("a.anomaly_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def anomalies(cur, medicine_id, category, anomaly_type, date_from, date_to, order_sql, limit, offset):
    where, params = _anomaly_where(medicine_id, category, anomaly_type, date_from, date_to)
    base = f"FROM medicine_demand_anomalies a JOIN medicines m ON m.medicine_id = a.medicine_id{where}"
    cur.execute(f"SELECT COUNT(*) AS n {base}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT a.anomaly_date AS date, a.medicine_id, m.medicine_name, m.category, a.actual_demand, "
        f"a.expected_demand, a.anomaly_score, a.anomaly_type {base} ORDER BY {order_sql} LIMIT %s OFFSET %s",
        (*params, limit, offset))
    return cur.fetchall(), total


def anomaly_summary(cur, medicine_id, category, anomaly_type, date_from, date_to):
    where, params = _anomaly_where(medicine_id, category, anomaly_type, date_from, date_to)
    base = f"FROM medicine_demand_anomalies a JOIN medicines m ON m.medicine_id = a.medicine_id{where}"
    cur.execute(f"SELECT a.anomaly_type, COUNT(*) AS n {base} GROUP BY a.anomaly_type ORDER BY n DESC", tuple(params))
    by_type = cur.fetchall()
    cur.execute(
        f"SELECT a.medicine_id, m.medicine_name, COUNT(*) AS anomaly_count {base} "
        f"GROUP BY a.medicine_id, m.medicine_name ORDER BY anomaly_count DESC, a.medicine_id LIMIT 5", tuple(params))
    return by_type, cur.fetchall()


def movement(cur, tier, category, search, order_sql):
    clauses, params = _catalog_where("v", None, category, search)
    if tier:
        clauses.append("v.volume_tier = %s"); params.append(tier)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT v.medicine_id, m.medicine_name, m.category, v.total_units_dispensed, v.volume_tier "
        f"FROM medicine_volume_tiers v JOIN medicines m ON m.medicine_id = v.medicine_id{where} "
        f"ORDER BY {order_sql}", tuple(params))
    return cur.fetchall()


def demand_by_medicine(cur, medicine_id, category, date_from, date_to, search, order_sql):
    """Per-medicine demand totals for reports (units_requested = DEMAND; issued/dispensed shown separately)."""
    where, params = demand_where(medicine_id, category, date_from, date_to)
    if search:
        where += (" AND " if where else " WHERE ") + "m.medicine_name LIKE %s"
        params.append(f"%{search}%")
    cur.execute(
        f"SELECT d.medicine_id, m.medicine_name, d.category, SUM(d.units_requested) AS total_requested, "
        f"SUM(d.units_issued) AS total_issued, SUM(d.units_dispensed) AS total_dispensed, "
        f"AVG(d.units_requested) AS avg_daily_requested, MAX(d.units_requested) AS peak_daily_requested, "
        f"COUNT(DISTINCT d.demand_date) AS days FROM medicine_demand d "
        f"JOIN medicines m ON m.medicine_id = d.medicine_id{where} "
        f"GROUP BY d.medicine_id, m.medicine_name, d.category ORDER BY {order_sql}", tuple(params))
    return cur.fetchall()
