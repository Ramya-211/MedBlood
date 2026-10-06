"""
blood_alert_queries.py

CURRENT-STATE alert and recommendation snapshots supplied with the dataset (single date
2024-12-31, confirmed during inspection), plus the inputs needed for forecast-based
recommendation rules. Mirrors medicine_alert_queries.py.
"""


def snapshot_dates(cur):
    cur.execute(
        "SELECT (SELECT MIN(alert_date) FROM blood_alerts) AS alerts_min, "
        "(SELECT MAX(alert_date) FROM blood_alerts) AS alerts_max, "
        "(SELECT MIN(rec_date) FROM blood_recommendations) AS recs_min, "
        "(SELECT MAX(rec_date) FROM blood_recommendations) AS recs_max")
    return cur.fetchone()


def _alert_filters(alert_type, severity, blood_group, rh_type, blood_component, date_from, date_to):
    clauses, params = [], []
    if alert_type:
        clauses.append("a.alert_type = %s"); params.append(alert_type)
    if severity:
        clauses.append("a.severity = %s"); params.append(severity)
    if blood_group:
        clauses.append("a.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("a.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("a.blood_component = %s"); params.append(blood_component)
    if date_from:
        clauses.append("a.alert_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("a.alert_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


_ALERT_ENRICH = (
    "FROM blood_alerts a "
    "LEFT JOIN blood_inventory i ON i.blood_group=a.blood_group AND i.rh_type=a.rh_type "
    "AND i.blood_component=a.blood_component AND i.inv_date = %s "
    "LEFT JOIN (SELECT blood_group, rh_type, blood_component, SUM(expiry_status = 'Expired') AS expired_batches, "
    "COALESCE(SUM(CASE WHEN expiry_status = 'Expired' THEN units_remaining END), 0) AS expired_units, "
    "SUM(expiry_status = 'Near Expiry') AS near_expiry_batches, "
    "COALESCE(SUM(CASE WHEN expiry_status = 'Near Expiry' THEN units_remaining END), 0) AS near_expiry_units "
    "FROM blood_batches GROUP BY blood_group, rh_type, blood_component) b "
    "ON b.blood_group=a.blood_group AND b.rh_type=a.rh_type AND b.blood_component=a.blood_component"
)


def alerts(cur, as_of, alert_type, severity, blood_group, rh_type, blood_component, date_from, date_to, order_sql,
           limit, offset):
    where, params = _alert_filters(alert_type, severity, blood_group, rh_type, blood_component, date_from, date_to)
    cur.execute(f"SELECT COUNT(*) AS n {_ALERT_ENRICH}{where}", (as_of, *params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT a.alert_id, a.alert_date, a.blood_group, a.rh_type, a.blood_component, a.alert_type, a.severity, "
        f"a.message, i.closing_stock, b.expired_batches, b.expired_units, b.near_expiry_batches, b.near_expiry_units "
        f"{_ALERT_ENRICH}{where} ORDER BY {order_sql} LIMIT %s OFFSET %s", (as_of, *params, limit, offset))
    return cur.fetchall(), total


def alert_summary(cur, blood_group, rh_type, blood_component):
    clauses, params = [], []
    if blood_group:
        clauses.append("a.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("a.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("a.blood_component = %s"); params.append(blood_component)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(f"SELECT a.alert_type, a.severity, COUNT(*) AS n FROM blood_alerts a{where} "
                f"GROUP BY a.alert_type, a.severity ORDER BY a.alert_type, a.severity", tuple(params))
    return cur.fetchall()


# ---------------------------------------------------------------- recommendations (supplied snapshot)
def _rec_filters(rec_type, severity, blood_group, rh_type, blood_component, date_from, date_to):
    clauses, params = [], []
    if rec_type:
        clauses.append("r.recommendation_type = %s"); params.append(rec_type)
    if severity:
        clauses.append("r.severity = %s"); params.append(severity)
    if blood_group:
        clauses.append("r.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("r.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("r.blood_component = %s"); params.append(blood_component)
    if date_from:
        clauses.append("r.rec_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("r.rec_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def recommendations(cur, as_of, rec_type, severity, blood_group, rh_type, blood_component, date_from, date_to,
                    order_sql, limit, offset):
    where, params = _rec_filters(rec_type, severity, blood_group, rh_type, blood_component, date_from, date_to)
    base = ("FROM blood_recommendations r LEFT JOIN blood_inventory i ON i.blood_group=r.blood_group "
            "AND i.rh_type=r.rh_type AND i.blood_component=r.blood_component AND i.inv_date = %s" + where)
    cur.execute(f"SELECT COUNT(*) AS n {base}", (as_of, *params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT r.recommendation_id, r.rec_date, r.blood_group, r.rh_type, r.blood_component, r.current_stock, "
        f"r.predicted_demand AS supplied_predicted_demand, r.days_of_cover, r.recommendation_type, r.severity, r.reason, "
        f"i.closing_stock AS current_stock_now {base} ORDER BY {order_sql} LIMIT %s OFFSET %s", (as_of, *params, limit, offset))
    return cur.fetchall(), total


def recommendation_summary(cur, blood_group, rh_type, blood_component):
    clauses, params = [], []
    if blood_group:
        clauses.append("r.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("r.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("r.blood_component = %s"); params.append(blood_component)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(f"SELECT r.recommendation_type, r.severity, COUNT(*) AS n FROM blood_recommendations r{where} "
                f"GROUP BY 1, 2 ORDER BY 1, 2", tuple(params))
    return cur.fetchall()


# ---------------------------------------------------------------- forecast-based recommendation inputs
def forecast_recommendation_inputs(cur, as_of, run_id, horizon, blood_group, rh_type, blood_component):
    clauses, params = [], []
    if blood_group:
        clauses.append("s.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("s.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("s.blood_component = %s"); params.append(blood_component)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        "SELECT s.blood_group, s.rh_type, s.blood_component, i.closing_stock, "
        "i.closing_stock / NULLIF(c.avg_daily_issued_30d, 0) AS days_of_cover, "
        "c.avg_daily_issued_30d, f.forecast_total, f.avg_first_7, f.avg_last_7, f.steps "
        "FROM (SELECT DISTINCT blood_group, rh_type, blood_component FROM blood_demand) s "
        "LEFT JOIN blood_inventory i ON i.blood_group=s.blood_group AND i.rh_type=s.rh_type "
        "AND i.blood_component=s.blood_component AND i.inv_date = %s "
        "LEFT JOIN (SELECT blood_group, rh_type, blood_component, AVG(units_issued) AS avg_daily_issued_30d "
        "FROM blood_demand WHERE demand_date > DATE_SUB(%s, INTERVAL 30 DAY) AND demand_date <= %s "
        "GROUP BY blood_group, rh_type, blood_component) c ON c.blood_group=s.blood_group AND c.rh_type=s.rh_type "
        "AND c.blood_component=s.blood_component "
        "LEFT JOIN (SELECT blood_group, rh_type, blood_component, "
        "SUM(CASE WHEN horizon_step <= %s THEN predicted_demand END) AS forecast_total, "
        "AVG(CASE WHEN horizon_step <= 7 THEN predicted_demand END) AS avg_first_7, "
        "AVG(CASE WHEN horizon_step > (SELECT MAX(horizon_step) FROM blood_forecasts WHERE run_id = %s) - 7 "
        "THEN predicted_demand END) AS avg_last_7, SUM(horizon_step <= %s) AS steps "
        "FROM blood_forecasts WHERE run_id = %s GROUP BY blood_group, rh_type, blood_component) f "
        "ON f.blood_group=s.blood_group AND f.rh_type=s.rh_type AND f.blood_component=s.blood_component"
        f"{where} ORDER BY s.blood_group, s.rh_type, s.blood_component",
        (as_of, as_of, as_of, horizon, run_id, horizon, run_id, *params))
    return cur.fetchall()
