"""
blood_service.py

Business logic for Blood: demand analysis, supply/collection analysis, supply-vs-demand
comparison, forecasting (model comparison, historical BACKTEST, model-generated FUTURE
forecasts) and the dashboard. Mirrors medicine_service.py's structure and guarantees.

DEMAND = units_requested (blood_demand). SUPPLY = donation_volume (blood_collection).
INVENTORY = closing_stock (blood_inventory). FORECAST = model-generated blood_forecasts rows.
These four concepts are never merged into one number anywhere in this file.
"""

import json
from datetime import timedelta

import numpy as np

from app.config import get_settings
from app.database.db import db_cursor
from app.database.queries import blood_demand_queries as dq
from app.database.queries import blood_forecast_queries as fq
from app.database.queries import blood_inventory_queries as iq
from app.database.queries import blood_alert_queries as aq
from app.database.queries import blood_supply_queries as sq
from app.services.blood_common import as_of_date, meta, near_expiry_days, validate_segment
from app.utils.cache import cached
from app.utils.errors import BadRequestError, NotFoundError
from app.utils.query_helpers import page, period_days, resolve_sort, validate_range

MOVING_AVERAGE_WINDOWS = (7, 14, 30, 60, 90)
FORECAST_TREND_THRESHOLD = 0.05
BACKTEST_ROW_SORT = {"target_date": "target_date", "origin_date": "a.avp_date", "abs_error": "abs_error",
                     "error": "a.prediction_error", "actual": "a.actual_demand", "predicted": "a.predicted_demand"}
DEMAND_REPORT_SORT = {"total": "total_requested", "average": "avg_daily_requested", "peak": "peak_daily_requested"}


def _kwargs(blood_group, rh_type, blood_component):
    return dict(blood_group=blood_group, rh_type=rh_type, blood_component=blood_component)


# ============================================================================ filters
def get_filters():
    def load():
        with db_cursor() as cur:
            segs = dq.segments(cur)
            bounds = dq.demand_date_bounds(cur)
            bt = fq.backtest_bounds(cur)
            bts = sq.blood_types(cur)
        return segs, bounds, bt, bts

    segs, bounds, bt, bts = cached("blood:filters", 60, load)
    return {
        "blood_groups": sorted({s["blood_group"] for s in segs}), "rh_types": sorted({s["rh_type"] for s in segs}),
        "blood_components": sorted({s["blood_component"] for s in segs}), "segments": segs, "supply_blood_types": bts,
        "demand_date_range": {"min": bounds["min_date"], "max": bounds["max_date"]},
        "backtest_target_date_range": {
            "min": bt["first_origin"] + timedelta(days=1) if bt["first_origin"] else None,
            "max": bt["last_origin"] + timedelta(days=1) if bt["last_origin"] else None},
        "moving_average_windows": list(MOVING_AVERAGE_WINDOWS),
        "note": "No state/district/city/location fields exist anywhere in this module.",
        "meta": meta(as_of_date()),
    }


# ============================================================================ demand
def demand_series(granularity, blood_group, rh_type, blood_component, date_from, date_to, by_segment, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = dq.demand_series(cur, granularity, blood_group, rh_type, blood_component, d_from, d_to,
                                       by_segment, limit, offset)
    for r in rows:
        r["days_in_full_period"] = period_days(r["period_start"], granularity)
        r["is_complete_period"] = r["days_covered"] >= r["days_in_full_period"]
    return page(rows, total, limit, offset, granularity=granularity,
                metric_definitions={"units_requested": "DEMAND (units requested by patients/clinical need)",
                                    "units_issued": "units issued against requests",
                                    "units_transfused": "units actually transfused"},
                meta=meta())


def demand_summary(blood_group, rh_type, blood_component, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        kpi, days = dq.demand_kpis(cur, blood_group, rh_type, blood_component, d_from, d_to)
        ranks = dq.rankings(cur, blood_group, rh_type, blood_component, d_from, d_to)
        anomaly_by_type, _ = dq.anomaly_summary(cur, blood_group, rh_type, blood_component, d_from, d_to)
    n_days = kpi["days"] or 0
    total_requested = int(kpi["total_requested"])
    return {"kpis": {"total_requested": total_requested, "total_issued": int(kpi["total_issued"]),
                    "total_transfused": int(kpi["total_transfused"]), "total_emergency_requests": int(kpi["total_emergency"]),
                    "total_routine_requests": int(kpi["total_routine"]), "days_covered": n_days,
                    "segments": kpi["segments"], "first_date": kpi["first_date"], "last_date": kpi["last_date"],
                    "average_daily_requested": round(total_requested / n_days, 4) if n_days else None,
                    "peak_day": days["peak_day"], "lowest_day": days["lowest_day"]},
            "highest_demand_segments": ranks[:5], "lowest_demand_segments": list(reversed(ranks[-5:])) if ranks else [],
            "anomalies_in_range": {"total": sum(r["n"] for r in anomaly_by_type), "by_type": anomaly_by_type},
            "meta": meta()}


def demand_rankings(blood_group, rh_type, blood_component, date_from, date_to, limit):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        ranks = dq.rankings(cur, blood_group, rh_type, blood_component, d_from, d_to)
    return {"highest": ranks[:limit], "lowest": list(reversed(ranks[-limit:])), "total_segments": len(ranks), "meta": meta()}


def demand_variability(blood_group, rh_type, blood_component, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = dq.variability(cur, blood_group, rh_type, blood_component, d_from, d_to)
    return {"items": rows, "total": len(rows),
            "definition": "coefficient_of_variation = sample std of daily units_requested / mean daily units_requested",
            "meta": meta()}


def moving_average(window, blood_group, rh_type, blood_component, date_from, date_to):
    if window not in MOVING_AVERAGE_WINDOWS:
        raise BadRequestError(f"window must be one of {list(MOVING_AVERAGE_WINDOWS)}.")
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = dq.moving_average(cur, window, blood_group, rh_type, blood_component, d_from, d_to)
    for r in rows:
        r["window_complete"] = r["points_in_window"] >= window
    return {"window_days": window, "items": rows, "total": len(rows),
            "definition": f"Trailing {window}-day mean of total daily units_requested. Descriptive of the past only.",
            "meta": meta()}


def demand_growth(period, blood_group, rh_type, blood_component):
    gran = "weekly" if period == "week" else "monthly"
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        bounds = dq.demand_date_bounds(cur)
        lookback = 84 if period == "week" else 130
        rows, _ = dq.demand_series(cur, gran, blood_group, rh_type, blood_component,
                                   bounds["max_date"] - timedelta(days=lookback), None, True, 100000, 0)
    by_seg, overall = {}, {}
    for r in rows:
        if r["days_covered"] < period_days(r["period_start"], gran):
            continue
        key = (r["blood_group"], r["rh_type"], r["blood_component"])
        by_seg.setdefault(key, []).append(r)
        overall[r["period_start"]] = overall.get(r["period_start"], 0) + int(r["units_requested"])

    def change(cur_v, prev_v):
        return round((cur_v - prev_v) / prev_v * 100, 4) if prev_v else None

    items = []
    for (bg, rh, comp), lst in sorted(by_seg.items()):
        lst.sort(key=lambda x: x["period_start"])
        if len(lst) < 2:
            continue
        cur_r, prev_r = lst[-1], lst[-2]
        pct = change(int(cur_r["units_requested"]), int(prev_r["units_requested"]))
        items.append({"blood_group": bg, "rh_type": rh, "blood_component": comp,
                      "current_period_start": cur_r["period_start"], "current_units_requested": int(cur_r["units_requested"]),
                      "previous_period_start": prev_r["period_start"], "previous_units_requested": int(prev_r["units_requested"]),
                      "change_units": int(cur_r["units_requested"]) - int(prev_r["units_requested"]),
                      "change_percent": pct, "direction": _direction(pct)})
    periods = sorted(overall)
    overall_row = None
    if len(periods) >= 2:
        c, p = overall[periods[-1]], overall[periods[-2]]
        overall_row = {"current_period_start": periods[-1], "current_units_requested": c,
                       "previous_period_start": periods[-2], "previous_units_requested": p,
                       "change_units": c - p, "change_percent": change(c, p), "direction": _direction(change(c, p))}
    return {"period": period, "overall": overall_row, "items": items, "total": len(items), "meta": meta()}


def _direction(pct):
    if pct is None:
        return None
    return "Increasing" if pct > 0 else ("Decreasing" if pct < 0 else "Stable")


def demand_trends(blood_group, rh_type, blood_component):
    """DATASET LIMITATION: no precomputed trend table was supplied for Blood (unlike Medicine's
    medicine_trend_analysis); computed live here from blood_demand_features using the same
    documented rule (implied change over the period vs. mean demand, +/-5% threshold)."""
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = dq.trends(cur, blood_group, rh_type, blood_component)
    for r in rows:
        mean_d = float(r["mean_demand"]) if r["mean_demand"] else 0
        implied_change = float(r["trend_slope"]) * period_days_full() if r["trend_slope"] is not None else None
        pct = (implied_change / mean_d) if (implied_change is not None and mean_d) else None
        r["trend_direction"] = ("Increasing" if pct and pct > FORECAST_TREND_THRESHOLD else
                                "Decreasing" if pct and pct < -FORECAST_TREND_THRESHOLD else "Stable")
    return {"items": rows, "total": len(rows), "counts": _count_by(rows, "trend_direction"),
            "definition": ("Computed live (no precomputed table supplied): mean of the supplied per-day trend_slope "
                           "projected across the full history, compared to mean demand with a +/-5% threshold -- "
                           "same rule Medicine's supplied trend analysis uses."),
            "meta": meta()}


def period_days_full():
    with db_cursor() as cur:
        b = dq.demand_date_bounds(cur)
    return (b["max_date"] - b["min_date"]).days + 1


def _count_by(rows, key):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def demand_seasonality(blood_group, rh_type, blood_component):
    """DATASET LIMITATION: no precomputed seasonality table was supplied for Blood; computed live
    from blood_demand_features (same definition as Medicine's supplied seasonality_index)."""
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows = dq.seasonality(cur, blood_group, rh_type, blood_component)
    grouped = {}
    for r in rows:
        key = (r["blood_group"], r["rh_type"], r["blood_component"])
        grouped.setdefault(key, {"blood_group": key[0], "rh_type": key[1], "blood_component": key[2], "months": []})
        grouped[key]["months"].append({"month": r["month"], "seasonality_index": r["seasonality_index"]})
    profiles = []
    for prof in grouped.values():
        idx = [m for m in prof["months"] if m["seasonality_index"] is not None]
        if idx:
            peak, low = max(idx, key=lambda m: m["seasonality_index"]), min(idx, key=lambda m: m["seasonality_index"])
            prof["peak_month"], prof["peak_index"] = peak["month"], peak["seasonality_index"]
            prof["lowest_month"], prof["lowest_index"] = low["month"], low["seasonality_index"]
        profiles.append(prof)
    return {"items": rows, "profiles": profiles, "total": len(rows),
            "definition": "seasonality_index per month = average of (past 7-day mean / past 90-day mean) of daily demand.",
            "meta": meta()}


def demand_anomalies(blood_group, rh_type, blood_component, date_from, date_to, sort, order, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, {"date": "f.feature_date", "score": "ABS(f.anomaly_score)",
                                           "actual": "f.daily_demand"}, "date")
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = dq.anomalies(cur, blood_group, rh_type, blood_component, d_from, d_to, order_sql, limit, offset)
        by_type, top = dq.anomaly_summary(cur, blood_group, rh_type, blood_component, d_from, d_to)
    return page(rows, total, limit, offset, summary={"by_type": by_type, "top_segments": top},
                definition=("Computed live from blood_demand_features.anomaly_flag (no precomputed anomalies table "
                            "supplied for Blood): flagged when |z| > 2.5 vs the trailing 30-day mean/std."),
                meta=meta())


def demand_movement(blood_component, sort, order):
    with db_cursor() as cur:
        rows = dq.movement(cur, blood_component, None)
    return {"items": rows, "total": len(rows), "counts": _count_by(rows, "volume_tier"),
            "definition": ("DATASET LIMITATION: no precomputed volume-tier table was supplied for Blood (unlike "
                           "Medicine). Computed live using the SAME rule: segments ranked by total units_requested "
                           "over the full history; top third = Fast Moving, middle third = Medium Moving, bottom "
                           "third = Slow Moving."),
            "meta": meta()}


def demand_report_rows(blood_group, rh_type, blood_component, date_from, date_to, sort, order):
    d_from, d_to = validate_range(date_from, date_to)
    order_sql = resolve_sort(sort, order, DEMAND_REPORT_SORT, "total") if sort else "total_requested DESC"
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        return dq.demand_by_segment(cur, blood_group, rh_type, blood_component, d_from, d_to, order_sql)


# ============================================================================ supply / collection
def supply_series(granularity, blood_type, date_from, date_to, by_type, limit, offset):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        rows, total = sq.supply_series(cur, granularity, blood_type, d_from, d_to, by_type, limit, offset)
    return page(rows, total, limit, offset, granularity=granularity, metric="donation_volume (SUPPLY, not demand)",
                meta=meta())


def supply_summary(blood_type, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    with db_cursor() as cur:
        kpi = sq.supply_summary(cur, blood_type, d_from, d_to)
        by_type = sq.supply_by_type(cur, d_from, d_to)
    return {"kpis": {"total_donation_volume": int(kpi["total_donation_volume"]), "days_covered": kpi["days"],
                    "blood_types": kpi["blood_types"], "first_date": kpi["first_date"], "last_date": kpi["last_date"]},
            "by_blood_type": by_type, "meta": meta()}


def supply_vs_demand(date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    as_of = as_of_date()
    with db_cursor() as cur:
        rows = sq.demand_vs_supply(cur, d_from, d_to)
        inv_rows = {}
        for r in iq.current_inventory(cur, as_of, None, None, None, None, "i.blood_group", 1000, 0)[0]:
            key = f"{r['blood_group']}{'+' if r['rh_type']=='Positive' else '-'}"
            inv_rows[key] = inv_rows.get(key, 0) + int(r["closing_stock"])
    for r in rows:
        r["current_available_inventory"] = inv_rows.get(r["blood_type"])
        if r["total_demand_requested"] is not None and r["total_supply_donation_volume"] is not None:
            r["supply_minus_demand"] = r["total_supply_donation_volume"] - r["total_demand_requested"]
        else:
            r["supply_minus_demand"] = None
    return {"as_of_date": as_of, "items": rows, "total": len(rows),
            "definitions": {"total_demand_requested": "DEMAND: sum of blood_demand.units_requested (patient need)",
                            "total_supply_donation_volume": "SUPPLY: sum of blood_collection.donation_volume (collected)",
                            "current_available_inventory": "INVENTORY: latest blood_inventory.closing_stock"},
            "limitation": ("blood_collection has no blood_component breakdown and is keyed by combined blood_type "
                           "(e.g. 'O+'), so this comparison is only possible at the blood_group+Rh level -- demand is "
                           "summed across all components to match. blood_collection is also a SYNTHETIC PLACEHOLDER "
                           "(no real donation data was supplied). Demand and supply are shown side by side; they are "
                           "never combined into a single number."),
            "meta": meta(as_of)}


# ============================================================================ forecasting
def _metrics_public(m):
    if not m or not m.get("n"):
        return {"n": 0, "mae": None, "rmse": None, "r2": None, "bias": None, "total_actual": None, "total_predicted": None}
    return {"n": int(m["n"]), "mae": m["mae"], "rmse": m["rmse"], "r2": m["r2"], "bias": m["mean_error"],
            "total_actual": m["total_actual"], "total_predicted": m["total_predicted"]}


def _origin_bounds(date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    return (d_from - timedelta(days=1) if d_from else None, d_to - timedelta(days=1) if d_to else None)


PRIMARY_ALGORITHMS = ("Linear Regression", "Random Forest Regressor", "XGBoost Regressor")


def model_comparison():
    def load():
        with db_cursor() as cur:
            comp = fq.model_comparison(cur)
            recomputed = fq.backtest_overall(cur, None, None, None, None, None)
            bounds = fq.backtest_bounds(cur)
            run = fq.latest_run(cur)
        return comp, recomputed, bounds, run

    comp, recomputed, bounds, run = cached("blood:model_comparison", 120, load)
    if not comp:
        raise NotFoundError("No model comparison metrics have been imported.")
    primary = [r for r in comp if r["model_name"] in PRIMARY_ALGORITHMS]
    baseline = [r for r in comp if r["model_name"] not in PRIMARY_ALGORITHMS]
    if not primary:
        raise NotFoundError("None of the three primary algorithms were found in the imported comparison.")
    best_rmse = min(primary, key=lambda r: r["rmse"])
    best_mae = min(primary, key=lambda r: r["mae"])
    best_r2 = max(primary, key=lambda r: r["r2"])
    items = [dict(r, is_best_rmse=r is best_rmse, is_best_mae=r is best_mae, is_best_r2=r is best_r2) for r in primary]
    rec = _metrics_public(recomputed)
    return {
        "items": items, "primary_algorithms": list(PRIMARY_ALGORITHMS),
        "internal_baseline_reference": {
            "note": ("A naive lag-1 baseline is computed for internal evaluation only -- it is not one of the three "
                    "primary project algorithms and is never selectable for forecasting."),
            "metrics": baseline[0] if baseline else None},
        "selected_model": best_rmse["model_name"],
        "selection_rule": "Lowest test-set RMSE among the three primary algorithms (metrics as supplied with the dataset).",
        "evaluation": {"split": "chronological hold-out test set (last 15% of rows)", "test_rows": bounds["n"],
                       "test_origin_date_range": [bounds["first_origin"], bounds["last_origin"]],
                       "metric_definitions": {"MAE": "mean absolute error (units/day)",
                                              "RMSE": "root mean squared error (units/day)", "R2": "coefficient of determination"}},
        "integrity_check": {"backtest_rows_recomputed_metrics": rec, "note": "Recomputed from stored actual-vs-predicted rows."},
        "forecast_model_in_use": run["model_name"] if run else None,
        "meta": meta(),
    }


def backtest(blood_group, rh_type, blood_component, date_from, date_to):
    o_from, o_to = _origin_bounds(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        overall = fq.backtest_overall(cur, blood_group, rh_type, blood_component, o_from, o_to)
        by_seg = fq.backtest_by_segment(cur, blood_group, rh_type, blood_component, o_from, o_to)
        bounds = fq.backtest_bounds(cur)
    return {"type": "HISTORICAL_BACKTEST", "overall": _metrics_public(overall),
            "by_segment": [dict(blood_group=r["blood_group"], rh_type=r["rh_type"], blood_component=r["blood_component"],
                                **_metrics_public(r)) for r in by_seg],
            "coverage": {"first_target_date": bounds["first_origin"] + timedelta(days=1) if bounds["first_origin"] else None,
                        "last_target_date": bounds["last_origin"] + timedelta(days=1) if bounds["last_origin"] else None},
            "definition": "Recomputed from the stored supplied hold-out predictions. HISTORICAL, not a future forecast.",
            "meta": meta()}


def actual_vs_predicted(granularity, blood_group, rh_type, blood_component, date_from, date_to, limit, offset):
    o_from, o_to = _origin_bounds(date_from, date_to)
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = fq.backtest_series(cur, granularity, blood_group, rh_type, blood_component, o_from, o_to, limit, offset)
        overall = fq.backtest_overall(cur, blood_group, rh_type, blood_component, o_from, o_to)
    return page(rows, total, limit, offset, type="HISTORICAL_BACKTEST", granularity=granularity,
                overall=_metrics_public(overall), meta=meta())


def backtest_rows(blood_group, rh_type, blood_component, date_from, date_to, sort, order, limit, offset):
    o_from, o_to = _origin_bounds(date_from, date_to)
    order_sql = resolve_sort(sort, order, BACKTEST_ROW_SORT, "target_date")
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        rows, total = fq.backtest_rows(cur, blood_group, rh_type, blood_component, o_from, o_to, order_sql, limit, offset)
    return page(rows, total, limit, offset, type="HISTORICAL_BACKTEST",
                definition="origin_date = when the prediction was made; target_date = origin_date + 1.", meta=meta())


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
            "message": "No model-generated forecast exists yet. Run `python -m app.ml.blood_ml train`.", "meta": meta()}


def _resolve_run(cur, run_id):
    run = fq.get_run(cur, run_id) if run_id else fq.latest_run(cur)
    if run_id and not run:
        raise NotFoundError(f"Forecast run {run_id} was not found.")
    return run


def _forecast_trend(series):
    if len(series) < 14:
        return {"direction": None, "note": "Fewer than 14 forecast days; trend not computed."}
    vals = np.array([float(s["predicted_demand"]) for s in series])
    first, last = vals[:7].mean(), vals[-7:].mean()
    pct = (last - first) / first if first else None
    slope = float(np.polyfit(np.arange(len(vals)), vals, 1)[0])
    direction = None if pct is None else ("Increasing" if pct > FORECAST_TREND_THRESHOLD
                                          else "Decreasing" if pct < -FORECAST_TREND_THRESHOLD else "Stable")
    return {"direction": direction, "change_percent_last7_vs_first7": None if pct is None else pct * 100,
            "avg_first_7_days": float(first), "avg_last_7_days": float(last), "slope_units_per_day": slope}


def future_forecast(blood_group, rh_type, blood_component, run_id, horizon, limit, offset):
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        run = _resolve_run(cur, run_id)
        if not run:
            return _no_run_payload()
        if horizon and horizon > run["horizon_days"]:
            raise BadRequestError(f"horizon must be between 1 and {run['horizon_days']} for run {run['run_id']}.")
        rows, total = fq.forecast_rows(cur, run["run_id"], blood_group, rh_type, blood_component, horizon, limit, offset)
        series = fq.forecast_by_date(cur, run["run_id"], blood_group, rh_type, blood_component, horizon)
        totals = fq.forecast_totals_by_segment(cur, run["run_id"], horizon, blood_group, rh_type, blood_component)
    return page(rows, total, limit, offset, available=True, type="MODEL_GENERATED_FORECAST",
                label="MODEL-GENERATED FORECAST (not observed data)", run=_run_public(run), series=series,
                totals_by_segment=totals, trend=_forecast_trend(series),
                caveats=["Recursive multi-step forecast: later steps use earlier predictions as inputs.",
                         "Forecasts model demand only; future collection/receipts are not modelled.",
                         "Trained on SYNTHETIC data."], meta=meta())


def forecast_overview(blood_group, rh_type, blood_component, history_days):
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        bounds = dq.demand_date_bounds(cur)
        start = bounds["max_date"] - timedelta(days=history_days - 1)
        hist, _ = dq.demand_series(cur, "daily", blood_group, rh_type, blood_component, start, None, False,
                                   history_days + 5, 0)
        bt_rows, _ = fq.backtest_series(cur, "daily", blood_group, rh_type, blood_component,
                                        start - timedelta(days=1), None, history_days + 5, 0)
        overall = fq.backtest_overall(cur, blood_group, rh_type, blood_component, None, None)
        run = fq.latest_run(cur)
        fc = fq.forecast_by_date(cur, run["run_id"], blood_group, rh_type, blood_component, None) if run else []
    return {
        "historical_actual": {"label": "OBSERVED HISTORICAL DEMAND",
                              "series": [{"date": r["period_start"], "units_requested": r["units_requested"]} for r in hist]},
        "historical_backtest": {"label": "HISTORICAL BACKTEST (supplied hold-out predictions vs actual)",
                                "series": [{"target_date": r["period_start"], "actual_demand": r["actual_demand"],
                                           "predicted_demand": r["predicted_demand"]} for r in bt_rows]},
        "future_forecast": {"label": "MODEL-GENERATED FORECAST (future, not observed)", "available": bool(run),
                            "run": _run_public(run) if run else None,
                            "series": [{"date": r["forecast_date"], "predicted_demand": r["predicted_demand"]} for r in fc],
                            "trend": _forecast_trend(fc) if fc else None},
        "backtest_metrics_overall": _metrics_public(overall), "meta": meta(),
    }


# ============================================================================ dashboard
def dashboard(blood_group, rh_type, blood_component, date_from, date_to):
    d_from, d_to = validate_range(date_from, date_to)
    as_of = as_of_date()
    settings = get_settings()
    horizon = settings.forecast_shortage_horizon_days
    near_days = near_expiry_days()
    with db_cursor() as cur:
        validate_segment(cur, blood_group, rh_type, blood_component)
        bounds = dq.demand_date_bounds(cur)
        max_date = bounds["max_date"]

        inv_rows, _ = iq.current_inventory(cur, as_of, blood_group, rh_type, blood_component, None, "i.blood_group", 1000, 0)
        inv_by_status = {}
        for r in inv_rows:
            inv_by_status.setdefault(r["stock_status"], []).append(r)
        batch = {r["expiry_status"]: r for r in iq.batch_status_summary(cur, as_of, near_days, blood_group, rh_type, blood_component)}
        run = fq.latest_run(cur)
        fc_totals = fq.forecast_totals_by_segment(cur, run["run_id"], horizon, blood_group, rh_type, blood_component) if run else []
        gen = {(r["alert_type"], r["severity"]): r["n"] for r in aq.alert_summary(cur, blood_group, rh_type, blood_component)}
        supply_kpi = sq.supply_summary(cur, None, d_from, d_to)
        demand_kpi, _ = dq.demand_kpis(cur, blood_group, rh_type, blood_component, d_from, d_to)

        w_from = d_from or (max_date - timedelta(weeks=26))
        m_from = d_from or (max_date.replace(day=1) - timedelta(days=365)).replace(day=1)
        weekly, _ = dq.demand_series(cur, "weekly", blood_group, rh_type, blood_component, w_from, d_to, False, 1000, 0)
        monthly, _ = dq.demand_series(cur, "monthly", blood_group, rh_type, blood_component, m_from, d_to, False, 1000, 0)
        o_from = d_from - timedelta(days=1) if d_from else None
        o_to = d_to - timedelta(days=1) if d_to else None
        avp, _ = fq.backtest_series(cur, "weekly", blood_group, rh_type, blood_component, o_from, o_to, 1000, 0)
        avp_overall = fq.backtest_overall(cur, blood_group, rh_type, blood_component, o_from, o_to)
        fc_daily = fq.forecast_by_date(cur, run["run_id"], blood_group, rh_type, blood_component, None) if run else []

    for r in weekly:
        r["is_complete_period"] = r["days_covered"] >= 7
    for r in monthly:
        r["is_complete_period"] = r["days_covered"] >= period_days(r["period_start"], "monthly")

    total_available = sum(int(r["closing_stock"]) for r in inv_rows)
    low_stock_segments = [{"blood_group": r["blood_group"], "rh_type": r["rh_type"], "blood_component": r["blood_component"],
                           "closing_stock": r["closing_stock"], "stock_status": r["stock_status"]}
                          for r in inv_rows if r["stock_status"] in ("Low", "Critical")]
    general_total = sum(gen.values())
    general_critical = sum(n for (t, s), n in gen.items() if s == "Critical")
    predicted_value = sum(float(r["forecast_total"] or 0) for r in fc_totals) if run and fc_totals else None
    supply_minus_demand = (int(supply_kpi["total_donation_volume"]) - int(demand_kpi["total_requested"])
                           if supply_kpi and demand_kpi else None)

    return {
        "kpis": {
            "total_available_units": {"value": total_available, "as_of_date": as_of, "note": "Sum of closing_stock (INVENTORY)."},
            "total_requested_units": {"value": int(demand_kpi["total_requested"]), "note": "DEMAND, over the selected date range."},
            "total_received_donated_units": {"value": int(supply_kpi["total_donation_volume"]), "note": "SUPPLY, over the selected date range."},
            "supply_minus_demand": {"value": supply_minus_demand,
                                    "note": "SUPPLY - DEMAND over the same range; shown for context only, not merged."},
            "predicted_demand": ({"value": predicted_value, "horizon_days": horizon, "unit": "units requested",
                                  "label": "MODEL-GENERATED FORECAST", "run_id": run["run_id"], "model_name": run["model_name"]}
                                 if run and predicted_value is not None else
                                 {"value": None, "message": "No model-generated forecast exists yet (run `python -m app.ml.blood_ml train`)."}),
            "low_stock_segments": {"count": len(low_stock_segments), "items": low_stock_segments[:10], "as_of_date": as_of},
            "near_expiry": {"batches": int(batch["Near Expiry"]["batches"]) if "Near Expiry" in batch else 0,
                            "units": int(batch["Near Expiry"]["units"]) if "Near Expiry" in batch else 0,
                            "expired_batches": int(batch["Expired"]["batches"]) if "Expired" in batch else 0,
                            "expired_units": int(batch["Expired"]["units"]) if "Expired" in batch else 0,
                            "near_expiry_days": near_days},
            "active_alerts": {"total": general_total, "critical": general_critical},
        },
        "charts": {
            "weekly_demand_trend": {"granularity": "weekly", "metric": "units_requested", "items": weekly},
            "monthly_demand_trend": {"granularity": "monthly", "metric": "units_requested", "items": monthly},
            "actual_vs_predicted": {
                "historical_backtest": {"label": "HISTORICAL BACKTEST", "items": avp, "overall": _metrics_public(avp_overall)},
                "future_forecast": {"label": "MODEL-GENERATED FORECAST", "available": bool(run), "items": fc_daily,
                                    "run_id": run["run_id"] if run else None}},
        },
        "filters_applied": {"blood_group": blood_group, "rh_type": rh_type, "blood_component": blood_component,
                            "date_from": d_from, "date_to": d_to},
        "meta": meta(as_of),
    }
