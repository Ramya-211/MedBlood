"""
blood_forecast_queries.py

Mirrors medicine_forecast_queries.py exactly, for blood segments (blood_group, rh_type,
blood_component). Supplied backtest semantics verified during inspection: avp_date is the
prediction ORIGIN date; actual_demand is the demand on origin_date + 1 (100% match on all
5,223 supplied rows). Sign convention: prediction_error = actual_demand - predicted_demand.
"""

TARGET = "DATE_ADD(a.avp_date, INTERVAL 1 DAY)"
TARGET_BUCKETS = {
    "daily": TARGET,
    "weekly": f"DATE_SUB({TARGET}, INTERVAL WEEKDAY({TARGET}) DAY)",
    "monthly": f"DATE_SUB({TARGET}, INTERVAL DAYOFMONTH({TARGET}) - 1 DAY)",
}


def _avp_where(blood_group, rh_type, blood_component, origin_from, origin_to):
    clauses, params = ["a.source = 'BACKTEST'"], []
    if blood_group:
        clauses.append("a.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("a.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("a.blood_component = %s"); params.append(blood_component)
    if origin_from:
        clauses.append("a.avp_date >= %s"); params.append(origin_from)
    if origin_to:
        clauses.append("a.avp_date <= %s"); params.append(origin_to)
    return " WHERE " + " AND ".join(clauses), params


_FROM_AVP = "FROM blood_actual_vs_predicted a"
_METRICS = (
    "COUNT(*) AS n, AVG(ABS(a.prediction_error)) AS mae, SQRT(AVG(a.prediction_error * a.prediction_error)) AS rmse, "
    "1 - SUM(POW(a.actual_demand - a.predicted_demand, 2)) / NULLIF(SUM(POW(a.actual_demand, 2)) "
    "- POW(SUM(a.actual_demand), 2) / COUNT(*), 0) AS r2, AVG(a.prediction_error) AS mean_error, "
    "SUM(a.actual_demand) AS total_actual, SUM(a.predicted_demand) AS total_predicted"
)


def model_comparison(cur):
    cur.execute("SELECT model_name, rmse, mae, r2 FROM blood_model_comparison ORDER BY rmse")
    return cur.fetchall()


def backtest_bounds(cur):
    cur.execute("SELECT MIN(avp_date) AS first_origin, MAX(avp_date) AS last_origin, COUNT(*) AS n, "
                "COUNT(DISTINCT CONCAT(blood_group,rh_type,blood_component)) AS segments "
                "FROM blood_actual_vs_predicted WHERE source = 'BACKTEST'")
    return cur.fetchone()


def backtest_overall(cur, blood_group, rh_type, blood_component, origin_from, origin_to):
    where, params = _avp_where(blood_group, rh_type, blood_component, origin_from, origin_to)
    cur.execute(f"SELECT {_METRICS} {_FROM_AVP}{where}", tuple(params))
    return cur.fetchone()


def backtest_by_segment(cur, blood_group, rh_type, blood_component, origin_from, origin_to):
    where, params = _avp_where(blood_group, rh_type, blood_component, origin_from, origin_to)
    cur.execute(f"SELECT a.blood_group, a.rh_type, a.blood_component, {_METRICS} {_FROM_AVP}{where} "
                f"GROUP BY a.blood_group, a.rh_type, a.blood_component ORDER BY a.blood_group, a.rh_type, a.blood_component",
                tuple(params))
    return cur.fetchall()


def backtest_series(cur, granularity, blood_group, rh_type, blood_component, origin_from, origin_to, limit, offset):
    bucket = TARGET_BUCKETS[granularity]
    where, params = _avp_where(blood_group, rh_type, blood_component, origin_from, origin_to)
    cur.execute(f"SELECT COUNT(*) AS n FROM (SELECT {bucket} AS period_start {_FROM_AVP}{where} "
                f"GROUP BY period_start) t", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT {bucket} AS period_start, SUM(a.actual_demand) AS actual_demand, SUM(a.predicted_demand) AS predicted_demand, "
        f"SUM(a.prediction_error) AS net_error, AVG(ABS(a.prediction_error)) AS mean_abs_error, COUNT(*) AS n_predictions, "
        f"COUNT(DISTINCT a.avp_date) AS days_covered {_FROM_AVP}{where} GROUP BY period_start "
        f"ORDER BY period_start LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def backtest_rows(cur, blood_group, rh_type, blood_component, origin_from, origin_to, order_sql, limit, offset):
    where, params = _avp_where(blood_group, rh_type, blood_component, origin_from, origin_to)
    cur.execute(f"SELECT COUNT(*) AS n {_FROM_AVP}{where}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT a.avp_date AS origin_date, {TARGET} AS target_date, a.blood_group, a.rh_type, a.blood_component, "
        f"a.actual_demand, a.predicted_demand, a.prediction_error, ABS(a.prediction_error) AS abs_error "
        f"{_FROM_AVP}{where} ORDER BY {order_sql} LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


# ---------------------------------------------------------------- future (model-generated) forecasts
def latest_run(cur):
    cur.execute("SELECT * FROM blood_forecast_runs ORDER BY run_id DESC LIMIT 1")
    return cur.fetchone()


def get_run(cur, run_id):
    cur.execute("SELECT * FROM blood_forecast_runs WHERE run_id = %s", (run_id,))
    return cur.fetchone()


def list_runs(cur):
    cur.execute("SELECT run_id, generated_at, model_name, trained_through_date, training_rows, horizon_days, "
                "selection_basis, notes FROM blood_forecast_runs ORDER BY run_id DESC")
    return cur.fetchall()


def _fc_where(run_id, blood_group, rh_type, blood_component, max_step):
    clauses, params = ["f.run_id = %s"], [run_id]
    if blood_group:
        clauses.append("f.blood_group = %s"); params.append(blood_group)
    if rh_type:
        clauses.append("f.rh_type = %s"); params.append(rh_type)
    if blood_component:
        clauses.append("f.blood_component = %s"); params.append(blood_component)
    if max_step:
        clauses.append("f.horizon_step <= %s"); params.append(max_step)
    return " WHERE " + " AND ".join(clauses), params


def forecast_rows(cur, run_id, blood_group, rh_type, blood_component, max_step, limit, offset):
    where, params = _fc_where(run_id, blood_group, rh_type, blood_component, max_step)
    base = f"FROM blood_forecasts f{where}"
    cur.execute(f"SELECT COUNT(*) AS n {base}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT f.run_id, f.blood_group, f.rh_type, f.blood_component, f.origin_date, f.forecast_date, f.horizon_step, "
        f"f.uses_predicted_inputs, f.predicted_demand {base} ORDER BY f.forecast_date, f.blood_group, f.rh_type, f.blood_component "
        f"LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def forecast_by_date(cur, run_id, blood_group, rh_type, blood_component, max_step):
    where, params = _fc_where(run_id, blood_group, rh_type, blood_component, max_step)
    cur.execute(f"SELECT f.forecast_date, f.horizon_step, SUM(f.predicted_demand) AS predicted_demand, "
                f"COUNT(*) AS segments FROM blood_forecasts f{where} GROUP BY f.forecast_date, f.horizon_step "
                f"ORDER BY f.forecast_date", tuple(params))
    return cur.fetchall()


def forecast_totals_by_segment(cur, run_id, max_step, blood_group=None, rh_type=None, blood_component=None):
    where, params = _fc_where(run_id, blood_group, rh_type, blood_component, max_step)
    cur.execute(
        f"SELECT f.blood_group, f.rh_type, f.blood_component, SUM(f.predicted_demand) AS forecast_total, "
        f"AVG(CASE WHEN f.horizon_step <= 7 THEN f.predicted_demand END) AS avg_first_7, "
        f"AVG(CASE WHEN f.horizon_step > (SELECT MAX(horizon_step) FROM blood_forecasts WHERE run_id = f.run_id) - 7 "
        f"THEN f.predicted_demand END) AS avg_last_7, COUNT(*) AS steps FROM blood_forecasts f{where} "
        f"GROUP BY f.blood_group, f.rh_type, f.blood_component ORDER BY f.blood_group, f.rh_type, f.blood_component",
        tuple(params))
    return cur.fetchall()
