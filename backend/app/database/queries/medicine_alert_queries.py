"""
medicine_alert_queries.py

Raw SQL for the CURRENT-STATE alert and recommendation snapshots supplied with the dataset
(tables medicine_alerts, medicine_expiry_alerts, medicine_recommendations; all dated at a
single snapshot date) plus the inputs needed by the forecast-based recommendation rules.

These are current-state records. They are never presented as history, and no dates are invented.
"""


def snapshot_dates(cur):
    cur.execute(
        "SELECT (SELECT MIN(alert_date) FROM medicine_alerts) AS alerts_min, "
        "(SELECT MAX(alert_date) FROM medicine_alerts) AS alerts_max, "
        "(SELECT MIN(alert_date) FROM medicine_expiry_alerts) AS expiry_alerts_min, "
        "(SELECT MAX(alert_date) FROM medicine_expiry_alerts) AS expiry_alerts_max, "
        "(SELECT MIN(rec_date) FROM medicine_recommendations) AS recs_min, "
        "(SELECT MAX(rec_date) FROM medicine_recommendations) AS recs_max")
    return cur.fetchone()


def _alert_filters(alias, alert_type, severity, medicine_id, category, search, date_from, date_to, date_col="alert_date"):
    clauses, params = [], []
    if alert_type:
        clauses.append(f"{alias}.alert_type = %s"); params.append(alert_type)
    if severity:
        clauses.append(f"{alias}.severity = %s"); params.append(severity)
    if medicine_id:
        clauses.append(f"{alias}.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if search:
        clauses.append(f"(m.medicine_name LIKE %s OR {alias}.message LIKE %s)"); params.extend([f"%{search}%"] * 2)
    if date_from:
        clauses.append(f"{alias}.{date_col} >= %s"); params.append(date_from)
    if date_to:
        clauses.append(f"{alias}.{date_col} <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


_ALERT_ENRICH = (
    "FROM medicine_alerts a JOIN medicines m ON m.medicine_id = a.medicine_id "
    "LEFT JOIN medicine_inventory i ON i.medicine_id = a.medicine_id AND i.inv_date = %s "
    "LEFT JOIN (SELECT medicine_id, SUM(expiry_status = 'Expired') AS expired_batches, "
    "COALESCE(SUM(CASE WHEN expiry_status = 'Expired' THEN units_remaining END), 0) AS expired_units, "
    "SUM(expiry_status = 'Near Expiry') AS near_expiry_batches, "
    "COALESCE(SUM(CASE WHEN expiry_status = 'Near Expiry' THEN units_remaining END), 0) AS near_expiry_units "
    "FROM medicine_batches GROUP BY medicine_id) b ON b.medicine_id = a.medicine_id "
    "LEFT JOIN medicine_demand_anomalies an ON an.medicine_id = a.medicine_id AND an.anomaly_date = a.alert_date"
)


def alerts(cur, as_of, alert_type, severity, medicine_id, category, search, date_from, date_to, order_sql, limit, offset):
    where, params = _alert_filters("a", alert_type, severity, medicine_id, category, search, date_from, date_to)
    cur.execute(f"SELECT COUNT(*) AS n {_ALERT_ENRICH}{where}", (as_of, *params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT a.alert_id, a.alert_date, a.medicine_id, m.medicine_name, m.category, a.alert_type, a.severity, "
        f"a.message, i.closing_stock, i.stock_status AS current_stock_status, b.expired_batches, b.expired_units, "
        f"b.near_expiry_batches, b.near_expiry_units, an.actual_demand AS anomaly_actual_demand, "
        f"an.expected_demand AS anomaly_expected_demand, an.anomaly_score, an.anomaly_type "
        f"{_ALERT_ENRICH}{where} ORDER BY {order_sql} LIMIT %s OFFSET %s", (as_of, *params, limit, offset))
    return cur.fetchall(), total


def alert_summary(cur, medicine_id, category):
    clauses, params = [], []
    if medicine_id:
        clauses.append("a.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(f"SELECT a.alert_type, a.severity, COUNT(*) AS n FROM medicine_alerts a "
                f"JOIN medicines m ON m.medicine_id = a.medicine_id{where} GROUP BY a.alert_type, a.severity "
                f"ORDER BY a.alert_type, a.severity", tuple(params))
    return cur.fetchall()


def expiry_alerts(cur, severity, medicine_id, category, search, date_from, date_to, max_days, order_sql, limit, offset):
    clauses, params = [], []
    if severity:
        clauses.append("e.severity = %s"); params.append(severity)
    if medicine_id:
        clauses.append("e.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if search:
        clauses.append("(m.medicine_name LIKE %s OR e.batch_id LIKE %s OR e.message LIKE %s)"); params.extend([f"%{search}%"] * 3)
    if date_from:
        clauses.append("e.alert_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("e.alert_date <= %s"); params.append(date_to)
    if max_days is not None:
        clauses.append("e.days_to_expiry <= %s"); params.append(max_days)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    base = ("FROM medicine_expiry_alerts e JOIN medicines m ON m.medicine_id = e.medicine_id "
            "JOIN medicine_batches b ON b.batch_id = e.batch_id" + where)
    cur.execute(f"SELECT COUNT(*) AS n {base}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT e.alert_id, e.alert_date, e.medicine_id, m.medicine_name, e.batch_id, b.batch_number, e.expiry_date, "
        f"e.days_to_expiry, e.severity, e.message, b.units_remaining, b.expiry_status AS batch_expiry_status "
        f"{base} ORDER BY {order_sql} LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def expiry_alert_summary(cur, medicine_id, category):
    clauses, params = [], []
    if medicine_id:
        clauses.append("e.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        f"SELECT e.severity, CASE WHEN e.days_to_expiry < 0 THEN 'Expired' ELSE 'Near Expiry' END AS alert_type, "
        f"COUNT(*) AS n, COALESCE(SUM(b.units_remaining), 0) AS units FROM medicine_expiry_alerts e "
        f"JOIN medicines m ON m.medicine_id = e.medicine_id JOIN medicine_batches b ON b.batch_id = e.batch_id{where} "
        f"GROUP BY e.severity, alert_type ORDER BY alert_type, e.severity", tuple(params))
    return cur.fetchall()


def combined_alerts(cur, alert_type, severity, medicine_id, category, search, date_from, date_to, order_sql, limit, offset):
    """UNION of medicine-level alerts and batch-level expiry alerts (used by the alert report)."""
    def part(kind):
        if kind == "GENERAL":
            where, params = _alert_filters("a", alert_type, severity, medicine_id, category, search, date_from, date_to)
            sql = ("SELECT 'GENERAL' AS alert_source, a.alert_id, a.alert_date, a.medicine_id, m.medicine_name, "
                   "a.alert_type, a.severity, a.message, NULL AS batch_id, NULL AS days_to_expiry "
                   f"FROM medicine_alerts a JOIN medicines m ON m.medicine_id = a.medicine_id{where}")
            return sql, params
        clauses, params = [], []
        etype = "CASE WHEN e.days_to_expiry < 0 THEN 'Expired' ELSE 'Near Expiry' END"
        if alert_type:
            clauses.append(f"{etype} = %s"); params.append(alert_type)
        if severity:
            clauses.append("e.severity = %s"); params.append(severity)
        if medicine_id:
            clauses.append("e.medicine_id = %s"); params.append(medicine_id)
        if category:
            clauses.append("m.category = %s"); params.append(category)
        if search:
            clauses.append("(m.medicine_name LIKE %s OR e.message LIKE %s)"); params.extend([f"%{search}%"] * 2)
        if date_from:
            clauses.append("e.alert_date >= %s"); params.append(date_from)
        if date_to:
            clauses.append("e.alert_date <= %s"); params.append(date_to)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (f"SELECT 'BATCH_EXPIRY' AS alert_source, e.alert_id, e.alert_date, e.medicine_id, m.medicine_name, "
               f"{etype} AS alert_type, e.severity, e.message, e.batch_id, e.days_to_expiry "
               f"FROM medicine_expiry_alerts e JOIN medicines m ON m.medicine_id = e.medicine_id{where}")
        return sql, params

    s1, p1 = part("GENERAL")
    s2, p2 = part("BATCH")
    union = f"({s1}) UNION ALL ({s2})"
    cur.execute(f"SELECT COUNT(*) AS n FROM ({union}) u", tuple(p1 + p2))
    total = cur.fetchone()["n"]
    cur.execute(f"SELECT u.* FROM ({union}) u ORDER BY {order_sql} LIMIT %s OFFSET %s", (*p1, *p2, limit, offset))
    return cur.fetchall(), total


# ---------------------------------------------------------------- recommendations (supplied snapshot)
def _rec_filters(rec_type, severity, medicine_id, category, search, date_from, date_to):
    clauses, params = [], []
    if rec_type:
        clauses.append("r.recommendation_type = %s"); params.append(rec_type)
    if severity:
        clauses.append("r.severity = %s"); params.append(severity)
    if medicine_id:
        clauses.append("r.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if search:
        clauses.append("(m.medicine_name LIKE %s OR r.reason LIKE %s)"); params.extend([f"%{search}%"] * 2)
    if date_from:
        clauses.append("r.rec_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("r.rec_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def recommendations(cur, as_of, rec_type, severity, medicine_id, category, search, date_from, date_to, order_sql, limit, offset):
    where, params = _rec_filters(rec_type, severity, medicine_id, category, search, date_from, date_to)
    base = ("FROM medicine_recommendations r JOIN medicines m ON m.medicine_id = r.medicine_id "
            "LEFT JOIN medicine_inventory i ON i.medicine_id = r.medicine_id AND i.inv_date = %s" + where)
    cur.execute(f"SELECT COUNT(*) AS n {base}", (as_of, *params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT r.recommendation_id, r.rec_date, r.medicine_id, m.medicine_name, m.category, r.recommendation_type, "
        f"r.severity, r.reason, r.recommended_action, i.closing_stock AS current_stock, i.stock_status AS current_stock_status "
        f"{base} ORDER BY {order_sql} LIMIT %s OFFSET %s", (as_of, *params, limit, offset))
    return cur.fetchall(), total


def recommendation_summary(cur, medicine_id, category):
    clauses, params = [], []
    if medicine_id:
        clauses.append("r.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(f"SELECT r.recommendation_type, r.severity, COUNT(*) AS n FROM medicine_recommendations r "
                f"JOIN medicines m ON m.medicine_id = r.medicine_id{where} GROUP BY 1, 2 ORDER BY 1, 2", tuple(params))
    return cur.fetchall()


# ---------------------------------------------------------------- forecast-based recommendation inputs
def forecast_recommendation_inputs(cur, as_of, run_id, horizon, medicine_id, category):
    clauses, params = [], []
    if medicine_id:
        clauses.append("m.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(
        "SELECT m.medicine_id, m.medicine_name, m.category, i.closing_stock, i.stock_status, "
        "c.avg_daily_issued_30d, f.forecast_total, f.avg_first_7, f.avg_last_7, f.steps, "
        "t.trend_direction FROM medicines m "
        "LEFT JOIN medicine_inventory i ON i.medicine_id = m.medicine_id AND i.inv_date = %s "
        "LEFT JOIN (SELECT medicine_id, AVG(units_issued) AS avg_daily_issued_30d FROM medicine_demand "
        "WHERE demand_date > DATE_SUB(%s, INTERVAL 30 DAY) AND demand_date <= %s GROUP BY medicine_id) c "
        "ON c.medicine_id = m.medicine_id "
        "LEFT JOIN (SELECT medicine_id, SUM(CASE WHEN horizon_step <= %s THEN predicted_demand END) AS forecast_total, "
        "AVG(CASE WHEN horizon_step <= 7 THEN predicted_demand END) AS avg_first_7, "
        "AVG(CASE WHEN horizon_step > (SELECT MAX(horizon_step) FROM medicine_forecasts WHERE run_id = %s) - 7 "
        "THEN predicted_demand END) AS avg_last_7, SUM(horizon_step <= %s) AS steps "
        "FROM medicine_forecasts WHERE run_id = %s GROUP BY medicine_id) f ON f.medicine_id = m.medicine_id "
        "LEFT JOIN medicine_trend_analysis t ON t.medicine_id = m.medicine_id"
        f"{where} ORDER BY m.medicine_id",
        (as_of, as_of, as_of, horizon, run_id, horizon, run_id, *params))
    return cur.fetchall()
