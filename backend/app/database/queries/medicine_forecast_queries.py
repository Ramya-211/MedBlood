"""
medicine_forecast_queries.py

Raw SQL for forecasting. TWO strictly separate data sources:
  * medicine_actual_vs_predicted  -> supplied historical BACKTEST rows (source is always 'BACKTEST')
  * medicine_forecasts (+ medicine_forecast_runs) -> model-generated FUTURE forecasts

Supplied backtest semantics: the file's `date` is the forecast ORIGIN date; `actual_demand` is the
demand on origin_date + 1 day (verified on all rows), so target_date = origin_date + 1.
Sign convention (supplied): prediction_error = actual_demand - predicted_demand.
"""

TARGET = "DATE_ADD(a.avp_date, INTERVAL 1 DAY)"
TARGET_BUCKETS = {
    "daily": TARGET,
    "weekly": f"DATE_SUB({TARGET}, INTERVAL WEEKDAY({TARGET}) DAY)",
    "monthly": f"DATE_SUB({TARGET}, INTERVAL DAYOFMONTH({TARGET}) - 1 DAY)",
}


def _avp_where(medicine_id, category, origin_from, origin_to):
    clauses, params = ["a.source = 'BACKTEST'"], []
    if medicine_id:
        clauses.append("a.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if origin_from:
        clauses.append("a.avp_date >= %s"); params.append(origin_from)
    if origin_to:
        clauses.append("a.avp_date <= %s"); params.append(origin_to)
    return " WHERE " + " AND ".join(clauses), params


_FROM_AVP = "FROM medicine_actual_vs_predicted a JOIN medicines m ON m.medicine_id = a.medicine_id"
_METRICS = (
    "COUNT(*) AS n, AVG(ABS(a.prediction_error)) AS mae, SQRT(AVG(a.prediction_error * a.prediction_error)) AS rmse, "
    "1 - SUM(POW(a.actual_demand - a.predicted_demand, 2)) / NULLIF(SUM(POW(a.actual_demand, 2)) "
    "- POW(SUM(a.actual_demand), 2) / COUNT(*), 0) AS r2, AVG(a.prediction_error) AS mean_error, "
    "SUM(a.actual_demand) AS total_actual, SUM(a.predicted_demand) AS total_predicted"
)


def model_comparison(cur):
    cur.execute("SELECT model_name, rmse, mae, r2 FROM medicine_model_comparison ORDER BY rmse")
    return cur.fetchall()


def backtest_bounds(cur):
    cur.execute("SELECT MIN(avp_date) AS first_origin, MAX(avp_date) AS last_origin, COUNT(*) AS n, "
                "COUNT(DISTINCT medicine_id) AS medicines FROM medicine_actual_vs_predicted WHERE source = 'BACKTEST'")
    return cur.fetchone()


def backtest_overall(cur, medicine_id, category, origin_from, origin_to):
    where, params = _avp_where(medicine_id, category, origin_from, origin_to)
    cur.execute(f"SELECT {_METRICS} {_FROM_AVP}{where}", tuple(params))
    return cur.fetchone()


def backtest_by_medicine(cur, medicine_id, category, origin_from, origin_to):
    where, params = _avp_where(medicine_id, category, origin_from, origin_to)
    cur.execute(f"SELECT a.medicine_id, m.medicine_name, m.category, {_METRICS} {_FROM_AVP}{where} "
                f"GROUP BY a.medicine_id, m.medicine_name, m.category ORDER BY a.medicine_id", tuple(params))
    return cur.fetchall()


def backtest_series(cur, granularity, medicine_id, category, origin_from, origin_to, limit, offset):
    bucket = TARGET_BUCKETS[granularity]
    where, params = _avp_where(medicine_id, category, origin_from, origin_to)
    cur.execute(f"SELECT COUNT(*) AS n FROM (SELECT {bucket} AS period_start {_FROM_AVP}{where} "
                f"GROUP BY period_start) t", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT {bucket} AS period_start, SUM(a.actual_demand) AS actual_demand, SUM(a.predicted_demand) AS predicted_demand, "
        f"SUM(a.prediction_error) AS net_error, AVG(ABS(a.prediction_error)) AS mean_abs_error, COUNT(*) AS n_predictions, "
        f"COUNT(DISTINCT a.avp_date) AS days_covered {_FROM_AVP}{where} GROUP BY period_start "
        f"ORDER BY period_start LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def backtest_rows(cur, medicine_id, category, origin_from, origin_to, order_sql, limit, offset):
    where, params = _avp_where(medicine_id, category, origin_from, origin_to)
    cur.execute(f"SELECT COUNT(*) AS n {_FROM_AVP}{where}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT a.avp_date AS origin_date, {TARGET} AS target_date, a.medicine_id, m.medicine_name, m.category, "
        f"a.actual_demand, a.predicted_demand, a.prediction_error, ABS(a.prediction_error) AS abs_error "
        f"{_FROM_AVP}{where} ORDER BY {order_sql} LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


# ---------------------------------------------------------------- future (model-generated) forecasts
def latest_run(cur):
    cur.execute("SELECT * FROM medicine_forecast_runs ORDER BY run_id DESC LIMIT 1")
    return cur.fetchone()


def get_run(cur, run_id):
    cur.execute("SELECT * FROM medicine_forecast_runs WHERE run_id = %s", (run_id,))
    return cur.fetchone()


def list_runs(cur):
    cur.execute("SELECT run_id, generated_at, model_name, trained_through_date, training_rows, horizon_days, "
                "selection_basis, notes FROM medicine_forecast_runs ORDER BY run_id DESC")
    return cur.fetchall()


def _fc_where(run_id, medicine_id, category, max_step):
    clauses, params = ["f.run_id = %s"], [run_id]
    if medicine_id:
        clauses.append("f.medicine_id = %s"); params.append(medicine_id)
    if category:
        clauses.append("m.category = %s"); params.append(category)
    if max_step:
        clauses.append("f.horizon_step <= %s"); params.append(max_step)
    return " WHERE " + " AND ".join(clauses), params


def forecast_rows(cur, run_id, medicine_id, category, max_step, limit, offset):
    where, params = _fc_where(run_id, medicine_id, category, max_step)
    base = f"FROM medicine_forecasts f JOIN medicines m ON m.medicine_id = f.medicine_id{where}"
    cur.execute(f"SELECT COUNT(*) AS n {base}", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT f.run_id, f.medicine_id, m.medicine_name, m.category, f.origin_date, f.forecast_date, f.horizon_step, "
        f"f.uses_predicted_inputs, f.predicted_demand {base} ORDER BY f.forecast_date, f.medicine_id LIMIT %s OFFSET %s",
        (*params, limit, offset))
    return cur.fetchall(), total


def forecast_by_date(cur, run_id, medicine_id, category, max_step):
    where, params = _fc_where(run_id, medicine_id, category, max_step)
    cur.execute(
        f"SELECT f.forecast_date, f.horizon_step, SUM(f.predicted_demand) AS predicted_demand, "
        f"COUNT(*) AS medicines FROM medicine_forecasts f JOIN medicines m ON m.medicine_id = f.medicine_id{where} "
        f"GROUP BY f.forecast_date, f.horizon_step ORDER BY f.forecast_date", tuple(params))
    return cur.fetchall()


def forecast_totals_by_medicine(cur, run_id, max_step, medicine_id=None, category=None):
    where, params = _fc_where(run_id, medicine_id, category, max_step)
    cur.execute(
        f"SELECT f.medicine_id, m.medicine_name, m.category, SUM(f.predicted_demand) AS forecast_total, "
        f"AVG(CASE WHEN f.horizon_step <= 7 THEN f.predicted_demand END) AS avg_first_7, "
        f"AVG(CASE WHEN f.horizon_step > (SELECT MAX(horizon_step) FROM medicine_forecasts WHERE run_id = f.run_id) - 7 "
        f"THEN f.predicted_demand END) AS avg_last_7, "
        f"COUNT(*) AS steps FROM medicine_forecasts f JOIN medicines m ON m.medicine_id = f.medicine_id{where} "
        f"GROUP BY f.medicine_id, m.medicine_name, m.category ORDER BY f.medicine_id", tuple(params))
    return cur.fetchall()
