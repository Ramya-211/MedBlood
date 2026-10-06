"""
blood_demand_queries.py

Raw, parameterized SQL for blood demand analysis (table: blood_demand).
DEMAND = units_requested (patients' clinical requirement), never donor/collection volume.
Segment key = (blood_group, rh_type, blood_component). No geographic grouping anywhere.
"""

BUCKETS = {
    "daily": "d.demand_date",
    "weekly": "DATE_SUB(d.demand_date, INTERVAL WEEKDAY(d.demand_date) DAY)",
    "monthly": "DATE_SUB(d.demand_date, INTERVAL DAYOFMONTH(d.demand_date) - 1 DAY)",
    "yearly": "MAKEDATE(YEAR(d.demand_date), 1)",
}


def demand_where(blood_group=None, rh_type=None, blood_component=None, date_from=None, date_to=None, with_dates=True):
    clauses, params = [], []
    if blood_group:
        clauses.append("d.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("d.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("d.blood_component = %s"); params.append(blood_component)
    if with_dates and date_from:
        clauses.append("d.demand_date >= %s"); params.append(date_from)
    if with_dates and date_to:
        clauses.append("d.demand_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


# ------------------------------------------------------------------ filters
def segments(cur):
    cur.execute("SELECT DISTINCT blood_group, rh_type, blood_component FROM blood_demand "
                "ORDER BY blood_group, rh_type, blood_component")
    return cur.fetchall()


def segment_exists(cur, blood_group=None, rh_type=None, blood_component=None):
    clauses, params = [], []
    if blood_group:
        clauses.append("blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("blood_component = %s"); params.append(blood_component)
    if not clauses:
        return True
    cur.execute(f"SELECT 1 AS x FROM blood_demand WHERE {' AND '.join(clauses)} LIMIT 1", tuple(params))
    return cur.fetchone() is not None


def demand_date_bounds(cur):
    cur.execute("SELECT MIN(demand_date) AS min_date, MAX(demand_date) AS max_date FROM blood_demand")
    return cur.fetchone()


def latest_inventory_date(cur):
    cur.execute("SELECT MAX(inv_date) AS d FROM blood_inventory")
    return cur.fetchone()["d"]


# ------------------------------------------------------------------ demand series
def demand_series(cur, granularity, blood_group, rh_type, blood_component, date_from, date_to, by_segment, limit, offset):
    bucket = BUCKETS[granularity]
    where, params = demand_where(blood_group, rh_type, blood_component, date_from, date_to)
    if by_segment:
        extra = ", d.blood_group, d.rh_type, d.blood_component"
        group = order = "period_start, d.blood_group, d.rh_type, d.blood_component"
        inner_group = "period_start, d.blood_group, d.rh_type, d.blood_component"
    else:
        extra, group, order, inner_group = "", "period_start", "period_start", "period_start"
    cur.execute(f"SELECT COUNT(*) AS n FROM (SELECT {bucket} AS period_start FROM blood_demand d{where} "
                f"GROUP BY {inner_group}) t", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT {bucket} AS period_start{extra}, SUM(d.units_requested) AS units_requested, "
        f"SUM(d.units_issued) AS units_issued, SUM(d.units_transfused) AS units_transfused, "
        f"SUM(d.emergency_requests) AS emergency_requests, SUM(d.routine_requests) AS routine_requests, "
        f"COUNT(DISTINCT d.demand_date) AS days_covered FROM blood_demand d{where} "
        f"GROUP BY {group} ORDER BY {order} LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def demand_kpis(cur, blood_group, rh_type, blood_component, date_from, date_to):
    where, params = demand_where(blood_group, rh_type, blood_component, date_from, date_to)
    cur.execute(
        f"SELECT COALESCE(SUM(d.units_requested),0) AS total_requested, COALESCE(SUM(d.units_issued),0) AS total_issued, "
        f"COALESCE(SUM(d.units_transfused),0) AS total_transfused, COALESCE(SUM(d.emergency_requests),0) AS total_emergency, "
        f"COALESCE(SUM(d.routine_requests),0) AS total_routine, COUNT(DISTINCT d.demand_date) AS days, "
        f"COUNT(DISTINCT CONCAT(d.blood_group,d.rh_type,d.blood_component)) AS segments, "
        f"MIN(d.demand_date) AS first_date, MAX(d.demand_date) AS last_date FROM blood_demand d{where}", tuple(params))
    kpi = cur.fetchone()
    days = {}
    for label, direction in (("peak_day", "DESC"), ("lowest_day", "ASC")):
        cur.execute(f"SELECT d.demand_date AS date, SUM(d.units_requested) AS units_requested FROM blood_demand d{where} "
                    f"GROUP BY d.demand_date ORDER BY units_requested {direction}, d.demand_date LIMIT 1", tuple(params))
        days[label] = cur.fetchone()
    return kpi, days


def rankings(cur, blood_group, rh_type, blood_component, date_from, date_to):
    where, params = demand_where(blood_group, rh_type, blood_component, date_from, date_to)
    cur.execute(
        f"SELECT d.blood_group, d.rh_type, d.blood_component, SUM(d.units_requested) AS total_requested, "
        f"AVG(d.units_requested) AS avg_daily_requested FROM blood_demand d{where} "
        f"GROUP BY d.blood_group, d.rh_type, d.blood_component ORDER BY total_requested DESC, d.blood_group", tuple(params))
    return cur.fetchall()


def variability(cur, blood_group, rh_type, blood_component, date_from, date_to):
    where, params = demand_where(blood_group, rh_type, blood_component, date_from, date_to)
    cur.execute(
        f"SELECT d.blood_group, d.rh_type, d.blood_component, COUNT(*) AS days, AVG(d.units_requested) AS mean_daily, "
        f"STDDEV_SAMP(d.units_requested) AS std_daily, MIN(d.units_requested) AS min_daily, MAX(d.units_requested) AS max_daily, "
        f"STDDEV_SAMP(d.units_requested) / NULLIF(AVG(d.units_requested), 0) AS coefficient_of_variation "
        f"FROM blood_demand d{where} GROUP BY d.blood_group, d.rh_type, d.blood_component "
        f"ORDER BY coefficient_of_variation DESC", tuple(params))
    return cur.fetchall()


def moving_average(cur, window, blood_group, rh_type, blood_component, date_from, date_to):
    n_prev = int(window) - 1
    inner_where, params = demand_where(blood_group, rh_type, blood_component, None, None, with_dates=False)
    outer, outer_params = [], []
    if date_from:
        outer.append("x.demand_date >= %s"); outer_params.append(date_from)
    if date_to:
        outer.append("x.demand_date <= %s"); outer_params.append(date_to)
    outer_where = (" WHERE " + " AND ".join(outer)) if outer else ""
    cur.execute(
        f"SELECT * FROM (SELECT t.demand_date, t.total_requested, AVG(t.total_requested) OVER w AS moving_average, "
        f"COUNT(*) OVER w AS points_in_window FROM (SELECT d.demand_date, SUM(d.units_requested) AS total_requested "
        f"FROM blood_demand d{inner_where} GROUP BY d.demand_date) t "
        f"WINDOW w AS (ORDER BY t.demand_date ROWS BETWEEN {n_prev} PRECEDING AND CURRENT ROW)) x{outer_where} "
        f"ORDER BY x.demand_date", tuple(params + outer_params))
    return cur.fetchall()


# ------------------------------------------------------------------ supplied full-history analytics (features table)
def _feat_where(alias, blood_group, rh_type, blood_component):
    clauses, params = [], []
    if blood_group:
        clauses.append(f"{alias}.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append(f"{alias}.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append(f"{alias}.blood_component = %s"); params.append(blood_component)
    return clauses, params


def seasonality(cur, blood_group, rh_type, blood_component):
    """Computed live from blood_demand_features (blood has no precomputed seasonality table like medicine)."""
    clauses, params = _feat_where("f", blood_group, rh_type, blood_component)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT f.blood_group, f.rh_type, f.blood_component, f.month_num AS month, "
        f"AVG(f.seasonality_index) AS seasonality_index FROM blood_demand_features f{where} "
        f"GROUP BY f.blood_group, f.rh_type, f.blood_component, f.month_num "
        f"ORDER BY f.blood_group, f.rh_type, f.blood_component, f.month_num", tuple(params))
    return cur.fetchall()


def trends(cur, blood_group, rh_type, blood_component):
    """Computed live from blood_demand_features (blood has no precomputed trend table like medicine's
    medicine_trend_analysis): mean of the supplied per-day trend_slope/growth_rate columns."""
    clauses, params = _feat_where("f", blood_group, rh_type, blood_component)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT f.blood_group, f.rh_type, f.blood_component, AVG(f.trend_slope) AS trend_slope, "
        f"AVG(f.growth_rate_7d) AS growth_rate_7d, AVG(f.growth_rate_30d) AS growth_rate_30d, "
        f"AVG(f.daily_demand) AS mean_demand FROM blood_demand_features f{where} "
        f"GROUP BY f.blood_group, f.rh_type, f.blood_component", tuple(params))
    return cur.fetchall()


def anomalies(cur, blood_group, rh_type, blood_component, date_from, date_to, order_sql, limit, offset):
    """Computed live from blood_demand_features.anomaly_flag (blood has no precomputed anomalies table)."""
    clauses, params = _feat_where("f", blood_group, rh_type, blood_component)
    clauses.append("f.anomaly_flag = 1")
    if date_from:
        clauses.append("f.feature_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("f.feature_date <= %s"); params.append(date_to)
    where = " WHERE " + " AND ".join(clauses)
    cur.execute(f"SELECT COUNT(*) AS n FROM blood_demand_features f{where}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT f.feature_date AS date, f.blood_group, f.rh_type, f.blood_component, f.daily_demand AS actual_demand, "
        f"f.rolling_mean_30 AS expected_demand, f.anomaly_score, "
        f"CASE WHEN f.anomaly_score > 0 THEN 'Demand Spike' ELSE 'Demand Drop' END AS anomaly_type "
        f"FROM blood_demand_features f{where} ORDER BY {order_sql} LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def anomaly_summary(cur, blood_group, rh_type, blood_component, date_from, date_to):
    clauses, params = _feat_where("f", blood_group, rh_type, blood_component)
    clauses.append("f.anomaly_flag = 1")
    if date_from:
        clauses.append("f.feature_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("f.feature_date <= %s"); params.append(date_to)
    where = " WHERE " + " AND ".join(clauses)
    cur.execute(
        f"SELECT CASE WHEN f.anomaly_score > 0 THEN 'Demand Spike' ELSE 'Demand Drop' END AS anomaly_type, COUNT(*) AS n "
        f"FROM blood_demand_features f{where} GROUP BY anomaly_type ORDER BY n DESC", tuple(params))
    by_type = cur.fetchall()
    cur.execute(
        f"SELECT f.blood_group, f.rh_type, f.blood_component, COUNT(*) AS anomaly_count FROM blood_demand_features f{where} "
        f"GROUP BY f.blood_group, f.rh_type, f.blood_component ORDER BY anomaly_count DESC LIMIT 5", tuple(params))
    return by_type, cur.fetchall()


def movement(cur, blood_component, order_sql):
    """DATASET LIMITATION: unlike Medicine, no precomputed volume-tier table was supplied for Blood.
    Computed live here using the SAME documented rule (rank by total requested units over full history;
    top third = Fast Moving, middle third = Medium Moving, bottom third = Slow Moving), applied per segment."""
    clauses, params = [], []
    if blood_component:
        clauses.append("blood_component = %s"); params.append(blood_component)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(f"SELECT blood_group, rh_type, blood_component, SUM(units_requested) AS total_units_requested "
                f"FROM blood_demand{where} GROUP BY blood_group, rh_type, blood_component "
                f"ORDER BY total_units_requested DESC", tuple(params))
    rows = cur.fetchall()
    n = len(rows)
    t1, t2 = n // 3, 2 * n // 3
    for i, r in enumerate(rows):
        r["volume_tier"] = "Fast Moving" if i < t1 else ("Medium Moving" if i < t2 else "Slow Moving")
    key = {"total": lambda r: -r["total_units_requested"], "medicine": lambda r: (r["blood_group"], r["rh_type"]),
          "tier": lambda r: {"Fast Moving": 0, "Medium Moving": 1, "Slow Moving": 2}[r["volume_tier"]]}
    return rows


def demand_by_segment(cur, blood_group, rh_type, blood_component, date_from, date_to, order_sql):
    where, params = demand_where(blood_group, rh_type, blood_component, date_from, date_to)
    cur.execute(
        f"SELECT d.blood_group, d.rh_type, d.blood_component, SUM(d.units_requested) AS total_requested, "
        f"SUM(d.units_issued) AS total_issued, SUM(d.units_transfused) AS total_transfused, "
        f"AVG(d.units_requested) AS avg_daily_requested, MAX(d.units_requested) AS peak_daily_requested, "
        f"COUNT(DISTINCT d.demand_date) AS days FROM blood_demand d{where} "
        f"GROUP BY d.blood_group, d.rh_type, d.blood_component ORDER BY {order_sql}", tuple(params))
    return cur.fetchall()
