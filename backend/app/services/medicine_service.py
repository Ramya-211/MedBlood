"""
medicine_service.py

Business logic for: filters, demand analysis (daily/weekly/monthly/yearly, trends, moving averages,
growth, seasonality, anomalies, movement tiers, variability), forecasting (model comparison,
historical BACKTEST, model-generated FUTURE forecasts) and the dashboard.

Every number returned comes from MySQL (the imported dataset or the stored model-generated forecast run).
Nothing is estimated or invented here; derived values (ratios, metrics) are computed from stored rows.
"""

import json
from datetime import timedelta

import numpy as np

from app.config import get_settings
from app.database.db import db_cursor
from app.database.queries import medicine_demand_queries as dq
from app.database.queries import medicine_forecast_queries as fq
from app.database.queries import medicine_inventory_queries as iq
from app.database.queries import medicine_alert_queries as aq
from app.services.medicine_common import (as_of_date, near_expiry_days, validate_entities, meta)
from app.utils.cache import cached
from app.utils.errors import BadRequestError, NotFoundError
from app.utils.query_helpers import page, period_days, resolve_sort, validate_range

MOVING_AVERAGE_WINDOWS = (7, 14, 30, 60, 90)
FORECAST_TREND_THRESHOLD = 0.05   # +/-5% change, same relative threshold the supplied trend analysis uses
TREND_SORT = {"medicine": "m.medicine_name", "medicine_id": "t.medicine_id", "slope": "t.trend_slope",
              "growth_7d": "t.growth_rate_7d", "growth_30d": "t.growth_rate_30d",
              "direction": "FIELD(t.trend_direction, 'Increasing', 'Stable', 'Decreasing')"}
ANOMALY_SORT = {"date": "a.anomaly_date", "score": "ABS(a.anomaly_score)", "actual": "a.actual_demand",
                "medicine": "m.medicine_name", "type": "a.anomaly_type"}
MOVEMENT_SORT = {"total": "v.total_units_dispensed", "medicine": "m.medicine_name", "medicine_id": "v.medicine_id",
                 "tier": "FIELD(v.volume_tier, 'Fast Moving', 'Medium Moving', 'Slow Moving')"}
BACKTEST_ROW_SORT = {"target_date": "target_date", "origin_date": "a.avp_date", "medicine": "m.medicine_name",
                     "abs_error": "abs_error", "error": "a.prediction_error", "actual": "a.actual_demand",
                     "predicted": "a.predicted_demand"}
DEMAND_REPORT_SORT = {"total": "total_requested", "medicine": "m.medicine_name", "medicine_id": "d.medicine_id",
                      "average": "avg_daily_requested", "peak": "peak_daily_requested"}


# ============================================================================ filters
def get_filters():
    def load():
        with db_cursor() as cur:
            meds = dq.list_medicines(cur)
            bounds = dq.demand_date_bounds(cur)
            bt = fq.backtest_bounds(cur)
        return meds, bounds, bt

    meds, bounds, bt = cached("med:filters", 60, load)
    return {
        "medicines": meds,
        "categories": sorted({m["category"] for m in meds}),
        "demand_date_range": {"min": bounds["min_date"], "max": bounds["max_date"]},
        "backtest_target_date_range": {
            "min": bt["first_origin"] + timedelta(days=1) if bt["first_origin"] else None,
            "max": bt["last_origin"] + timedelta(days=1) if bt["last_origin"] else None},
        "moving_average_windows": list(MOVING_AVERAGE_WINDOWS),
        "meta": meta(as_of_date()),
    }


# ============================================================================ demand
def demand_series(granularity, medicine_id, category, date_from, date_to, by_medicine, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = dq.demand_series(cur, granularity, medicine_id, category, d_from, d_to, by_medicine, limit, offset)
    for r in rows:
        r["days_in_full_period"] = period_days(r["period_start"], granularity)
        r["is_complete_period"] = r["days_covered"] >= r["days_in_full_period"]
    return page(rows, total, limit, offset, granularity=granularity,
                metric_definitions={"units_requested": "DEMAND (units requested)",
                                    "units_issued": "units issued against requests",
                                    "units_dispensed": "units dispensed to patients"},
                period_note="period_start is the first day of the week (Monday) / month / year. "
                            "is_complete_period=false marks periods cut by the data range or a date filter.",
                meta=meta())


def demand_summary(medicine_id, category, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        kpi, days = dq.demand_kpis(cur, medicine_id, category, d_from, d_to)
        ranks = dq.rankings(cur, medicine_id, category, d_from, d_to)
        anomaly_by_type, _ = dq.anomaly_summary(cur, medicine_id, category, None, d_from, d_to)
        trends = dq.trends(cur, None, medicine_id, category, None, "t.medicine_id")
        tiers = dq.movement(cur, None, category, None, "v.medicine_id")
        if medicine_id:
            tiers = [t for t in tiers if t["medicine_id"] == medicine_id]
    n_days = kpi["days"] or 0
    total_requested = int(kpi["total_requested"])
    return {
        "kpis": {
            "total_requested": total_requested, "total_issued": int(kpi["total_issued"]),
            "total_dispensed": int(kpi["total_dispensed"]), "days_covered": n_days,
            "medicines": kpi["medicines"], "first_date": kpi["first_date"], "last_date": kpi["last_date"],
            "average_daily_requested": round(total_requested / n_days, 4) if n_days else None,
            "peak_day": days["peak_day"], "lowest_day": days["lowest_day"],
        },
        "highest_demand_medicines": ranks[:5],
        "lowest_demand_medicines": list(reversed(ranks[-5:])) if ranks else [],
        "anomalies_in_range": {"total": sum(r["n"] for r in anomaly_by_type), "by_type": anomaly_by_type},
        "trend_counts_full_history": _count_by(trends, "trend_direction"),
        "movement_counts_full_history": _count_by(tiers, "volume_tier"),
        "notes": ["trend_counts and movement_counts come from the supplied full-history (2021-2024) analyses and do "
                  "not change with the date filter."],
        "meta": meta(),
    }


def _count_by(rows, key):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def demand_rankings(medicine_id, category, date_from, date_to, limit):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        ranks = dq.rankings(cur, medicine_id, category, d_from, d_to)
    return {"highest": ranks[:limit], "lowest": list(reversed(ranks[-limit:])), "total_medicines": len(ranks),
            "meta": meta()}


def demand_variability(medicine_id, category, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = dq.variability(cur, medicine_id, category, d_from, d_to)
    return {"items": rows, "total": len(rows),
            "definition": "coefficient_of_variation = sample std of daily units_requested / mean daily units_requested",
            "meta": meta()}


def moving_average(window, medicine_id, category, date_from, date_to):
    if window not in MOVING_AVERAGE_WINDOWS:
        raise BadRequestError(f"window must be one of {list(MOVING_AVERAGE_WINDOWS)}.")
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = dq.moving_average(cur, window, medicine_id, category, d_from, d_to)
    for r in rows:
        r["window_complete"] = r["points_in_window"] >= window
    return {"window_days": window, "items": rows, "total": len(rows),
            "definition": (f"Trailing {window}-day mean of total daily units_requested (window includes the current "
                           f"day). This is a descriptive analytic of the past; it is not a forecast. Rows with "
                           f"window_complete=false are at the very start of the data."),
            "meta": meta()}


def demand_growth(period, medicine_id, category):
    gran = "weekly" if period == "week" else "monthly"
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        bounds = dq.demand_date_bounds(cur)
        lookback = 84 if period == "week" else 130
        rows, _ = dq.demand_series(cur, gran, medicine_id, category, bounds["max_date"] - timedelta(days=lookback),
                                   None, True, 100000, 0)
    by_med, overall = {}, {}
    for r in rows:
        if r["days_covered"] < period_days(r["period_start"], gran):
            continue  # only COMPLETE periods are compared
        by_med.setdefault((r["medicine_id"], r["medicine_name"]), []).append(r)
        overall[r["period_start"]] = overall.get(r["period_start"], 0) + int(r["units_requested"])

    def change(cur_v, prev_v):
        return round((cur_v - prev_v) / prev_v * 100, 4) if prev_v else None

    items = []
    for (mid, name), lst in sorted(by_med.items()):
        lst.sort(key=lambda x: x["period_start"])
        if len(lst) < 2:
            continue
        cur_r, prev_r = lst[-1], lst[-2]
        items.append({"medicine_id": mid, "medicine_name": name,
                      "current_period_start": cur_r["period_start"], "current_units_requested": int(cur_r["units_requested"]),
                      "previous_period_start": prev_r["period_start"], "previous_units_requested": int(prev_r["units_requested"]),
                      "change_units": int(cur_r["units_requested"]) - int(prev_r["units_requested"]),
                      "change_percent": change(int(cur_r["units_requested"]), int(prev_r["units_requested"])),
                      "direction": _direction(change(int(cur_r["units_requested"]), int(prev_r["units_requested"])))})
    periods = sorted(overall)
    overall_row = None
    if len(periods) >= 2:
        c, p = overall[periods[-1]], overall[periods[-2]]
        overall_row = {"current_period_start": periods[-1], "current_units_requested": c,
                       "previous_period_start": periods[-2], "previous_units_requested": p,
                       "change_units": c - p, "change_percent": change(c, p), "direction": _direction(change(c, p))}
    return {"period": period, "overall": overall_row, "items": items, "total": len(items),
            "definition": (f"Compares the latest COMPLETE {period} with the complete {period} before it, using summed "
                           f"units_requested. Partial periods at the end of the data are excluded."),
            "meta": meta()}


def _direction(pct):
    if pct is None:
        return None
    return "Increasing" if pct > 0 else ("Decreasing" if pct < 0 else "Stable")


def demand_trends(direction, medicine_id, category, search, sort, order):
    order_sql = resolve_sort(sort, order, TREND_SORT, "medicine_id")
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = dq.trends(cur, direction, medicine_id, category, search, order_sql)
    return {"items": rows, "total": len(rows), "counts": _count_by(rows, "trend_direction"),
            "definition": ("Supplied full-history analysis: linear fit of daily demand over 2021-2024. Increasing / "
                           "Decreasing when the fitted change over the period exceeds +/-5% of mean demand, else "
                           "Stable. growth_rate_7d / growth_rate_30d are the supplied averages of daily growth rates."),
            "meta": meta()}


def demand_seasonality(medicine_id, category):
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows = dq.seasonality(cur, medicine_id, category)
    summary = {}
    for r in rows:
        summary.setdefault(r["medicine_id"], {"medicine_id": r["medicine_id"], "medicine_name": r["medicine_name"],
                                              "category": r["category"], "months": []})["months"].append(r)
    profiles = []
    for s in summary.values():
        idx = [m for m in s["months"] if m["seasonality_index"] is not None]
        if idx:
            peak = max(idx, key=lambda m: m["seasonality_index"])
            low = min(idx, key=lambda m: m["seasonality_index"])
            s["peak_month"], s["peak_index"] = peak["month"], peak["seasonality_index"]
            s["lowest_month"], s["lowest_index"] = low["month"], low["seasonality_index"]
            s["seasonal_range"] = peak["seasonality_index"] - low["seasonality_index"]
        profiles.append(s)
    return {"items": rows, "profiles": profiles, "total": len(rows),
            "definition": ("Supplied analysis: seasonality_index per calendar month = average of (past 7-day mean / "
                           "past 90-day mean) of daily demand. Values above 1 mean demand runs above its recent norm "
                           "in that month."),
            "meta": meta()}


def demand_anomalies(medicine_id, category, anomaly_type, date_from, date_to, sort, order, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, ANOMALY_SORT, "date")
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = dq.anomalies(cur, medicine_id, category, anomaly_type, d_from, d_to, order_sql, limit, offset)
        by_type, top = dq.anomaly_summary(cur, medicine_id, category, anomaly_type, d_from, d_to)
    return page(rows, total, limit, offset, summary={"by_type": by_type, "top_medicines": top},
                definition=("Supplied anomaly detection: a day is flagged when |z| > 2.5, where z = (actual demand - "
                            "trailing 30-day mean) / trailing 30-day std. score > 0 => Demand Spike, < 0 => Demand Drop."),
                meta=meta())


def demand_movement(tier, category, search, sort, order):
    order_sql = resolve_sort(sort, order, MOVEMENT_SORT, "total") if sort else "v.total_units_dispensed DESC"
    with db_cursor() as cur:
        validate_entities(cur, None, category)
        rows = dq.movement(cur, tier, category, search, order_sql)
    return {"items": rows, "total": len(rows), "counts": _count_by(rows, "volume_tier"),
            "definition": ("Supplied classification over the FULL 2021-2024 period: medicines ranked by total units "
                           "dispensed; top third = Fast Moving, middle third = Medium Moving, bottom third = Slow Moving. "
                           "It is a medicine-level, static classification and does not change with date filters."),
            "meta": meta()}


def demand_report_rows(medicine_id, category, date_from, date_to, search, sort, order):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, DEMAND_REPORT_SORT, "total") if sort else "total_requested DESC"
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        return dq.demand_by_medicine(cur, medicine_id, category, d_from, d_to, search, order_sql)


# ============================================================================ forecasting
def _metrics_public(m):
    if not m or not m.get("n"):
        return {"n": 0, "mae": None, "rmse": None, "r2": None, "bias": None, "total_actual": None, "total_predicted": None}
    return {"n": int(m["n"]), "mae": m["mae"], "rmse": m["rmse"], "r2": m["r2"], "bias": m["mean_error"],
            "total_actual": m["total_actual"], "total_predicted": m["total_predicted"]}


def _origin_bounds(date_from, date_to):
    """API filters are on TARGET dates (the day the demand occurred); stored rows are keyed by origin = target - 1."""
    d_from, d_to = validate_range(date_from, date_to)
    return (d_from - timedelta(days=1) if d_from else None, d_to - timedelta(days=1) if d_to else None)


def model_comparison():
    def load():
        with db_cursor() as cur:
            comp = fq.model_comparison(cur)
            recomputed = fq.backtest_overall(cur, None, None, None, None)
            bounds = fq.backtest_bounds(cur)
            run = fq.latest_run(cur)
        return comp, recomputed, bounds, run

    comp, recomputed, bounds, run = cached("med:model_comparison", 120, load)
    if not comp:
        raise NotFoundError("No model comparison metrics have been imported.")
    best_rmse = min(comp, key=lambda r: r["rmse"])
    best_mae = min(comp, key=lambda r: r["mae"])
    best_r2 = max(comp, key=lambda r: r["r2"])
    items = [dict(r, is_best_rmse=r is best_rmse, is_best_mae=r is best_mae, is_best_r2=r is best_r2) for r in comp]
    rec = _metrics_public(recomputed)
    matches = None
    if rec["n"]:
        matches = (abs(rec["rmse"] - best_rmse["rmse"]) < 1e-6 and abs(rec["mae"] - best_rmse["mae"]) < 1e-6
                   and abs(rec["r2"] - best_rmse["r2"]) < 1e-6)
    return {
        "items": items,
        "selected_model": best_rmse["model_name"],
        "selection_rule": "Lowest test-set RMSE among the evaluated models (metrics as supplied with the dataset).",
        "evaluation": {"split": "chronological hold-out test set (last 15% of rows)", "test_rows": bounds["n"],
                       "test_origin_date_range": [bounds["first_origin"], bounds["last_origin"]],
                       "metric_definitions": {"MAE": "mean absolute error (units/day)",
                                              "RMSE": "root mean squared error (units/day)",
                                              "R2": "coefficient of determination"}},
        "integrity_check": {"backtest_rows_recomputed_metrics": rec,
                            "matches_selected_model_metrics": matches,
                            "note": "Metrics recomputed from the stored actual-vs-predicted rows and compared with the supplied comparison."},
        "forecast_model_in_use": run["model_name"] if run else None,
        "meta": meta(),
    }


def backtest(medicine_id, category, date_from, date_to):
    o_from, o_to = _origin_bounds(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        overall = fq.backtest_overall(cur, medicine_id, category, o_from, o_to)
        by_med = fq.backtest_by_medicine(cur, medicine_id, category, o_from, o_to)
        bounds = fq.backtest_bounds(cur)
    return {
        "type": "HISTORICAL_BACKTEST",
        "overall": _metrics_public(overall),
        "by_medicine": [dict(medicine_id=r["medicine_id"], medicine_name=r["medicine_name"], category=r["category"],
                             **_metrics_public(r)) for r in by_med],
        "coverage": {"first_target_date": bounds["first_origin"] + timedelta(days=1) if bounds["first_origin"] else None,
                     "last_target_date": bounds["last_origin"] + timedelta(days=1) if bounds["last_origin"] else None},
        "definition": ("Metrics recomputed from the stored supplied hold-out predictions: MAE = mean |actual - predicted|, "
                       "RMSE = sqrt(mean (actual - predicted)^2), R2 = 1 - SSE/SST, bias = mean(actual - predicted) "
                       "(positive => under-prediction). These are HISTORICAL backtest results, not future forecasts."),
        "meta": meta(),
    }


def actual_vs_predicted(granularity, medicine_id, category, date_from, date_to, limit, offset):
    o_from, o_to = _origin_bounds(date_from, date_to)
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = fq.backtest_series(cur, granularity, medicine_id, category, o_from, o_to, limit, offset)
        overall = fq.backtest_overall(cur, medicine_id, category, o_from, o_to)
    return page(rows, total, limit, offset, type="HISTORICAL_BACKTEST", granularity=granularity,
                overall=_metrics_public(overall),
                definition=("period_start is based on the TARGET date (the day the demand occurred). actual_demand and "
                            "predicted_demand are summed over the selected medicines; net_error = actual - predicted."),
                meta=meta())


def backtest_rows(medicine_id, category, date_from, date_to, sort, order, limit, offset):
    o_from, o_to = _origin_bounds(date_from, date_to)
    order_sql = resolve_sort(sort, order, BACKTEST_ROW_SORT, "target_date")
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        rows, total = fq.backtest_rows(cur, medicine_id, category, o_from, o_to, order_sql, limit, offset)
    return page(rows, total, limit, offset, type="HISTORICAL_BACKTEST",
                definition="origin_date = when the prediction was made; target_date = origin_date + 1 (the day predicted).",
                meta=meta())


def _run_public(run):
    def js(v):
        return json.loads(v) if isinstance(v, (str, bytes)) else v

    repro = js(run["reproduction_check"]) or {}
    diffs = [d for m in (repro.get("models") or {}).values() if m.get("abs_diff") for d in m["abs_diff"].values()]
    return {"run_id": run["run_id"], "generated_at": run["generated_at"], "model_name": run["model_name"],
            "trained_through_date": run["trained_through_date"], "training_rows": run["training_rows"],
            "horizon_days": run["horizon_days"], "hyperparameters": js(run["hyperparameters"]),
            "selection_basis": run["selection_basis"], "notes": run["notes"],
            "reproduction_check": {"max_abs_metric_diff_vs_imported": max(diffs) if diffs else None,
                                   "feature_parity_max_abs_diff": repro.get("feature_parity_max_abs_diff")}}


def forecast_runs():
    with db_cursor() as cur:
        runs = fq.list_runs(cur)
    return {"items": runs, "total": len(runs), "meta": meta()}


def _no_run_payload():
    return {"available": False, "type": "MODEL_GENERATED_FORECAST", "items": [], "series": [], "total": 0,
            "message": ("No model-generated forecast exists yet. Generate one with "
                        "`python -m app.ml.medicine_ml train` (run from the backend folder)."), "meta": meta()}


def _resolve_run(cur, run_id):
    run = fq.get_run(cur, run_id) if run_id else fq.latest_run(cur)
    if run_id and not run:
        raise NotFoundError(f"Forecast run {run_id} was not found.")
    return run


def _forecast_trend(series):
    """series: list of {'horizon_step','predicted_demand'} totals per day."""
    if len(series) < 14:
        return {"direction": None, "note": "Fewer than 14 forecast days; trend not computed."}
    vals = np.array([float(s["predicted_demand"]) for s in series])
    first, last = vals[:7].mean(), vals[-7:].mean()
    pct = (last - first) / first if first else None
    slope = float(np.polyfit(np.arange(len(vals)), vals, 1)[0])
    direction = None if pct is None else ("Increasing" if pct > FORECAST_TREND_THRESHOLD
                                          else "Decreasing" if pct < -FORECAST_TREND_THRESHOLD else "Stable")
    return {"direction": direction, "change_percent_last7_vs_first7": None if pct is None else pct * 100,
            "avg_first_7_days": float(first), "avg_last_7_days": float(last), "slope_units_per_day": slope,
            "method": "Compares the mean of the first 7 and last 7 forecast days (+/-5% => Increasing/Decreasing) "
                      "and a least-squares slope over the horizon."}


def future_forecast(medicine_id, category, run_id, horizon, limit, offset):
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        run = _resolve_run(cur, run_id)
        if not run:
            return _no_run_payload()
        if horizon and horizon > run["horizon_days"]:
            raise BadRequestError(f"horizon must be between 1 and {run['horizon_days']} for run {run['run_id']}.")
        rows, total = fq.forecast_rows(cur, run["run_id"], medicine_id, category, horizon, limit, offset)
        series = fq.forecast_by_date(cur, run["run_id"], medicine_id, category, horizon)
        totals = fq.forecast_totals_by_medicine(cur, run["run_id"], horizon, medicine_id, category)
    return page(rows, total, limit, offset, available=True, type="MODEL_GENERATED_FORECAST",
                label="MODEL-GENERATED FORECAST (not observed data)", run=_run_public(run), series=series,
                totals_by_medicine=totals, trend=_forecast_trend(series),
                caveats=["Recursive multi-step forecast: steps after the first use earlier predictions as inputs, so "
                         "uncertainty grows with the horizon.",
                         "Forecasts model demand only; they do not include future stock receipts.",
                         "Trained on SYNTHETIC data."], meta=meta())


def forecast_overview(medicine_id, category, history_days):
    """Three separately labelled series: observed history, historical backtest, future model forecast."""
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        bounds = dq.demand_date_bounds(cur)
        start = bounds["max_date"] - timedelta(days=history_days - 1)
        hist, _ = dq.demand_series(cur, "daily", medicine_id, category, start, None, False, history_days + 5, 0)
        bt_rows, _ = fq.backtest_series(cur, "daily", medicine_id, category, start - timedelta(days=1), None,
                                        history_days + 5, 0)
        overall = fq.backtest_overall(cur, medicine_id, category, None, None)
        run = fq.latest_run(cur)
        fc = fq.forecast_by_date(cur, run["run_id"], medicine_id, category, None) if run else []
    return {
        "historical_actual": {"label": "OBSERVED HISTORICAL DEMAND", "series": [
            {"date": r["period_start"], "units_requested": r["units_requested"]} for r in hist]},
        "historical_backtest": {"label": "HISTORICAL BACKTEST (supplied hold-out predictions vs actual)", "series": [
            {"target_date": r["period_start"], "actual_demand": r["actual_demand"],
             "predicted_demand": r["predicted_demand"]} for r in bt_rows]},
        "future_forecast": {"label": "MODEL-GENERATED FORECAST (future, not observed)", "available": bool(run),
                            "run": _run_public(run) if run else None,
                            "series": [{"date": r["forecast_date"], "predicted_demand": r["predicted_demand"]} for r in fc],
                            "trend": _forecast_trend(fc) if fc else None},
        "backtest_metrics_overall": _metrics_public(overall),
        "meta": meta(),
    }


# ============================================================================ dashboard
def dashboard(medicine_id, category, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    as_of = as_of_date()
    settings = get_settings()
    horizon = settings.forecast_shortage_horizon_days
    near_days = near_expiry_days()
    with db_cursor() as cur:
        validate_entities(cur, medicine_id, category)
        bounds = dq.demand_date_bounds(cur)
        max_date = bounds["max_date"]

        meds = [m for m in dq.list_medicines(cur)
                if (not medicine_id or m["medicine_id"] == medicine_id) and (not category or m["category"] == category)]

        inv = {r["stock_status"]: r for r in iq.inventory_summary(cur, as_of, category, medicine_id)}
        batch = {r["expiry_status"]: r for r in iq.batch_status_summary(cur, as_of, near_days, medicine_id, category)}
        run = fq.latest_run(cur)
        fc_totals = fq.forecast_totals_by_medicine(cur, run["run_id"], horizon, medicine_id, category) if run else []
        gen = {(r["alert_type"], r["severity"]): r["n"] for r in aq.alert_summary(cur, medicine_id, category)}
        exp = aq.expiry_alert_summary(cur, medicine_id, category)

        w_from = d_from or (max_date - timedelta(weeks=26))
        m_from = d_from or (max_date.replace(day=1) - timedelta(days=365)).replace(day=1)
        weekly, _ = dq.demand_series(cur, "weekly", medicine_id, category, w_from, d_to, False, 1000, 0)
        monthly, _ = dq.demand_series(cur, "monthly", medicine_id, category, m_from, d_to, False, 1000, 0)
        o_from = d_from - timedelta(days=1) if d_from else None
        o_to = d_to - timedelta(days=1) if d_to else None
        avp, _ = fq.backtest_series(cur, "weekly", medicine_id, category, o_from, o_to, 1000, 0)
        avp_overall = fq.backtest_overall(cur, medicine_id, category, o_from, o_to)
        fc_daily = fq.forecast_by_date(cur, run["run_id"], medicine_id, category, None) if run else []

    for r in weekly:
        r["is_complete_period"] = r["days_covered"] >= 7
    for r in monthly:
        r["is_complete_period"] = r["days_covered"] >= period_days(r["period_start"], "monthly")

    def count(status):
        return int(inv[status]["medicines"]) if status in inv else 0

    def units(d, status):
        return int(d[status]["units"]) if status in d else 0

    general_total = sum(gen.values())
    general_critical = sum(n for (t, s), n in gen.items() if s == "Critical")
    expiry_total = sum(r["n"] for r in exp)
    expiry_critical = sum(r["n"] for r in exp if r["severity"] == "Critical")
    predicted_value = sum(float(r["forecast_total"] or 0) for r in fc_totals) if run and fc_totals else None

    return {
        "kpis": {
            "total_medicines": len(meds),
            "current_inventory": {"units": sum(int(v["units"]) for v in inv.values()), "as_of_date": as_of,
                                  "note": "Sum of closing_stock from the stock ledger (medicine_inventory)."},
            "low_critical_stock": {"count": count("Low") + count("Critical"), "low": count("Low"),
                                   "critical": count("Critical"), "normal": count("Normal"),
                                   "overstock": count("Overstock"), "as_of_date": as_of},
            "near_expiry": {"batches": int(batch["Near Expiry"]["batches"]) if "Near Expiry" in batch else 0,
                            "units": units(batch, "Near Expiry"), "near_expiry_days": near_days,
                            "expired_batches": int(batch["Expired"]["batches"]) if "Expired" in batch else 0,
                            "expired_units": units(batch, "Expired"),
                            "note": "From the batch ledger (medicine_batches)."},
            "predicted_demand": ({"value": predicted_value, "horizon_days": horizon, "unit": "units requested",
                                  "label": "MODEL-GENERATED FORECAST", "run_id": run["run_id"],
                                  "model_name": run["model_name"],
                                  "period": [fc_daily[0]["forecast_date"], fc_daily[horizon - 1]["forecast_date"]]
                                  if len(fc_daily) >= horizon else None}
                                 if run and predicted_value is not None else
                                 {"value": None, "message": "No model-generated forecast exists yet "
                                                            "(run `python -m app.ml.medicine_ml train`)."}),
            "active_alerts": {"total": general_total + expiry_total, "critical": general_critical + expiry_critical,
                              "medicine_level": general_total, "batch_expiry_level": expiry_total,
                              "note": "Current-state alert snapshot supplied with the dataset."},
        },
        "charts": {
            "weekly_demand_trend": {"granularity": "weekly", "metric": "units_requested", "items": weekly},
            "monthly_demand_trend": {"granularity": "monthly", "metric": "units_requested", "items": monthly},
            "actual_vs_predicted": {
                "historical_backtest": {"label": "HISTORICAL BACKTEST", "granularity": "weekly", "items": avp,
                                        "overall": _metrics_public(avp_overall)},
                "future_forecast": {"label": "MODEL-GENERATED FORECAST", "available": bool(run), "items": fc_daily,
                                    "run_id": run["run_id"] if run else None}},
        },
        "filters_applied": {"medicine_id": medicine_id, "category": category, "date_from": d_from, "date_to": d_to},
        "meta": meta(as_of),
    }
