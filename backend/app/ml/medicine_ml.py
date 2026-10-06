"""
medicine_ml.py

ML layer for MEDICINE demand forecasting. Run as a CLI (NOT on every request):

    python -m app.ml.medicine_ml train [--horizon 30]

What it does
------------
1. Loads the supplied, imported feature table (medicine_demand_features) from MySQL.
2. REPRODUCES the supplied pipeline (same features, same chronological 70/15/15 split,
   same four candidate models and hyperparameters) and compares the resulting
   MAE / RMSE / R2 with the metrics imported from medicine_model_comparison.csv.
   The imported metrics are never overwritten; the comparison is stored as an audit record.
3. Selects the algorithm with the lowest imported RMSE (no hand-picking).
4. Refits that algorithm on ALL history (through the last date in the data) and saves it
   with joblib, so nothing is retrained when dashboards are opened.
5. Generates model-generated FUTURE forecasts recursively (each step feeds its own
   prediction back into the lag/rolling features) and stores them in
   medicine_forecast_runs / medicine_forecasts, separate from the supplied BACKTEST rows.

Target semantics (same as the supplied pipeline)
-----------------------------------------------
A feature row dated t uses information up to and including day t and predicts the demand
of day t+1.  Forecast rows therefore carry both origin_date (t) and forecast_date (t+1).
"""

import argparse
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.database.db import db_cursor  # noqa: E402

ARTIFACT_PATH = os.path.join(os.path.dirname(__file__), "artifacts", "medicine_model.joblib")

FEATURE_COLS = [
    "rolling_mean_7", "rolling_mean_30", "growth_rate_7d", "growth_rate_30d", "trend_slope",
    "month", "day_of_week", "seasonality_index", "lag_1", "lag_7", "lag_14", "lag_30",
    "anomaly_flag", "anomaly_score",
]
CAT_COLS = ["medicine_id", "category", "season"]
SEASON_MAP = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
              6: "Summer", 7: "Summer", 8: "Summer", 9: "Monsoon/Autumn", 10: "Monsoon/Autumn", 11: "Monsoon/Autumn"}

BASELINE = "Baseline (naive lag-1)"
LINEAR = "Linear Regression"
FOREST = "Random Forest Regressor"
XGB = "XGBoost Regressor"
TAIL_DAYS = 150  # > longest look-back needed by any feature (90-day mean + shift + growth windows)

HYPERPARAMETERS = {
    LINEAR: {},
    FOREST: {"n_estimators": 200, "max_depth": 10, "random_state": 42, "n_jobs": -1},
    XGB: {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8,
          "colsample_bytree": 0.8, "random_state": 42, "n_jobs": -1},
}


def make_model(name):
    if name == LINEAR:
        return LinearRegression()
    if name == FOREST:
        return RandomForestRegressor(**HYPERPARAMETERS[FOREST])
    if name == XGB:
        return XGBRegressor(**HYPERPARAMETERS[XGB])
    if name == BASELINE:
        return None
    raise ValueError(f"Unknown model: {name}")


# ----------------------------------------------------------------------------------------
# Data loading (from MySQL, raw SQL)
# ----------------------------------------------------------------------------------------
def load_feature_frame() -> pd.DataFrame:
    cols = ", ".join(f"f.{c}" for c in FEATURE_COLS if c not in ("month", "day_of_week"))
    sql = (f"SELECT f.feature_date AS date, f.medicine_id, m.category, f.daily_demand, {cols}, "
           "f.month_num AS month, f.day_of_week, f.season "
           "FROM medicine_demand_features f JOIN medicines m ON m.medicine_id = f.medicine_id "
           "ORDER BY f.medicine_id, f.feature_date")
    with db_cursor() as cur:
        cur.execute(sql)
        df = pd.DataFrame(cur.fetchall())
    df["date"] = pd.to_datetime(df["date"])
    for c in FEATURE_COLS + ["daily_demand"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_history() -> pd.DataFrame:
    with db_cursor() as cur:
        cur.execute("SELECT demand_date AS date, medicine_id, units_requested AS demand FROM medicine_demand "
                    "ORDER BY medicine_id, demand_date")
        df = pd.DataFrame(cur.fetchall())
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_imported_comparison() -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT model_name, rmse, mae, r2 FROM medicine_model_comparison")
        return {r["model_name"]: {"rmse": r["rmse"], "mae": r["mae"], "r2": r["r2"]} for r in cur.fetchall()}


# ----------------------------------------------------------------------------------------
# Supplied-pipeline reproduction
# ----------------------------------------------------------------------------------------
def build_matrix(df: pd.DataFrame):
    """Same operations, in the same order, as the supplied train_medicine_models.py."""
    df = df.sort_values(["medicine_id", "date"]).reset_index(drop=True)
    df["target_next_day_demand"] = df.groupby("medicine_id")["daily_demand"].shift(-1)
    d = df.copy()
    for c in ["medicine_id", "medicine_name", "category"]:
        if c in d.columns:
            d[c + "_orig"] = d[c]
    d["medicine_id_orig"] = df["medicine_id"]
    model_df = pd.get_dummies(d, columns=CAT_COLS, drop_first=False)
    dummy_cols = [c for c in model_df.columns
                  if any(c.startswith(p + "_") for p in CAT_COLS) and not c.endswith("_orig")]
    all_cols = FEATURE_COLS + dummy_cols
    model_df = model_df.dropna(subset=all_cols + ["target_next_day_demand"]).reset_index(drop=True)
    model_df.sort_values("date", inplace=True)
    model_df.reset_index(drop=True, inplace=True)
    return model_df, all_cols, dummy_cols


def chronological_split(model_df):
    n = len(model_df)
    return model_df.iloc[: int(n * 0.70)], model_df.iloc[int(n * 0.70): int(n * 0.85)], model_df.iloc[int(n * 0.85):]


def metrics(y_true, y_pred) -> dict:
    return {"rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "r2": float(r2_score(y_true, y_pred))}


def reproduce_supplied_metrics(model_df, all_cols, imported: dict) -> dict:
    train, _val, test = chronological_split(model_df)
    result = {}
    for name in (BASELINE, LINEAR, FOREST, XGB):
        if name == BASELINE:
            pred = test["lag_1"].values
        else:
            m = make_model(name)
            m.fit(train[all_cols], train["target_next_day_demand"])
            pred = m.predict(test[all_cols])
        got = metrics(test["target_next_day_demand"], pred)
        want = imported.get(name)
        result[name] = {
            "reproduced": got, "imported": want,
            "abs_diff": {k: abs(got[k] - want[k]) for k in got} if want else None,
        }
    return result


# ----------------------------------------------------------------------------------------
# Features for a single (medicine, last-day) point -- identical formulas to the supplied
# feature_engineering.py, evaluated only at the final row of a series tail.
# ----------------------------------------------------------------------------------------
def features_at_last(dates: pd.DatetimeIndex, values) -> dict:
    s = pd.Series(np.asarray(values, dtype=float))
    shifted = s.shift(1)
    i = len(s) - 1

    def growth(n):
        prev = shifted.shift(n).iloc[-1]
        cur = shifted.iloc[-1]
        if pd.isna(prev) or prev == 0:
            return np.nan
        return (cur - prev) / prev

    rm7 = shifted.rolling(7, min_periods=1).mean().iloc[-1]
    rm30 = shifted.rolling(30, min_periods=1).mean().iloc[-1]
    rm90 = shifted.rolling(90, min_periods=1).mean().iloc[-1]
    std30 = shifted.rolling(30, min_periods=2).std().iloc[-1]

    window = shifted.values[i - 30:i] if i >= 30 else None
    slope = np.nan
    if window is not None and not np.isnan(window).any():
        slope = np.polyfit(np.arange(30), window, 1)[0]

    score = np.nan if (pd.isna(std30) or std30 == 0) else (s.iloc[-1] - rm30) / std30
    return {
        "rolling_mean_7": rm7, "rolling_mean_30": rm30,
        "growth_rate_7d": growth(7), "growth_rate_30d": growth(30), "trend_slope": slope,
        "month": dates[-1].month, "day_of_week": dates[-1].dayofweek,
        "seasonality_index": np.nan if (pd.isna(rm90) or rm90 == 0) else rm7 / rm90,
        "lag_1": s.iloc[-2], "lag_7": s.iloc[-8], "lag_14": s.iloc[-15], "lag_30": s.iloc[-31],
        "anomaly_flag": int(abs(score) > 2.5) if not np.isnan(score) else 0,
        "anomaly_score": score,
    }


def feature_parity(history: pd.DataFrame, feature_df: pd.DataFrame, at_date, medicine_ids=None) -> float:
    """Max |recomputed - stored| over FEATURE_COLS at `at_date` across medicines (NaN==NaN)."""
    at_date = pd.Timestamp(at_date)
    worst = 0.0
    for mid, g in history.groupby("medicine_id"):
        if medicine_ids and mid not in medicine_ids:
            continue
        g = g[g["date"] <= at_date].tail(TAIL_DAYS)
        got = features_at_last(pd.DatetimeIndex(g["date"]), g["demand"].values)
        row = feature_df[(feature_df["medicine_id"] == mid) & (feature_df["date"] == at_date)]
        if row.empty:
            continue
        for c in FEATURE_COLS:
            a, b = got[c], row.iloc[0][c]
            if pd.isna(a) and pd.isna(b):
                continue
            if pd.isna(a) != pd.isna(b):
                return float("inf")
            worst = max(worst, abs(float(a) - float(b)))
    return worst


def build_row(feats: dict, medicine_id: str, category: str, all_cols: list, dtypes: dict) -> pd.DataFrame:
    row = {c: 0.0 for c in all_cols}
    for c in FEATURE_COLS:
        row[c] = feats[c]
    row[f"medicine_id_{medicine_id}"] = 1
    row[f"category_{category}"] = 1
    row[f"season_{SEASON_MAP[feats['month']]}"] = 1
    return pd.DataFrame([row], columns=all_cols).astype(dtypes)


def forecast_all(model, model_name, history, categories, all_cols, dtypes, horizon):
    """Recursive multi-step forecast. Returns rows: (medicine_id, origin, forecast_date, step, uses_predicted, value)."""
    out, clipped = [], 0
    for mid, g in history.groupby("medicine_id"):
        g = g.tail(TAIL_DAYS)
        dates = list(pd.DatetimeIndex(g["date"]))
        values = list(g["demand"].astype(float).values)
        for step in range(1, horizon + 1):
            feats = features_at_last(pd.DatetimeIndex(dates), values)
            if model_name == BASELINE:
                pred = float(feats["lag_1"])
            else:
                X = build_row(feats, mid, categories[mid], all_cols, dtypes)
                pred = float(model.predict(X)[0])
            if pred < 0:
                pred, clipped = 0.0, clipped + 1   # demand cannot be negative
            origin, target = dates[-1], dates[-1] + pd.Timedelta(days=1)
            out.append((mid, origin.date(), target.date(), step, 0 if step == 1 else 1, pred))
            dates.append(target)
            values.append(pred)
    return out, clipped


# ----------------------------------------------------------------------------------------
# Train + persist + forecast
# ----------------------------------------------------------------------------------------
def train(horizon: int = 30) -> dict:
    imported = load_imported_comparison()
    if not imported:
        raise RuntimeError("medicine_model_comparison is empty; run run_import.py first.")
    selected = min(imported, key=lambda k: imported[k]["rmse"])

    feature_df = load_feature_frame()
    history = load_history()
    model_df, all_cols, dummy_cols = build_matrix(feature_df)
    categories = feature_df.drop_duplicates("medicine_id").set_index("medicine_id")["category"].to_dict()
    trained_through = history["date"].max()

    print(f"Selected algorithm (lowest imported RMSE): {selected}")
    print("Reproducing the supplied pipeline for an audit comparison ...")
    repro = reproduce_supplied_metrics(model_df, all_cols, imported)
    for name, r in repro.items():
        d = r["abs_diff"]
        print(f"  {name:26s} reproduced RMSE={r['reproduced']['rmse']:.6f}  imported RMSE={r['imported']['rmse']:.6f}"
              f"  |diff| rmse={d['rmse']:.2e} mae={d['mae']:.2e} r2={d['r2']:.2e}")

    parity = feature_parity(history, feature_df, trained_through)
    print(f"Feature parity at {trained_through.date()} (recomputed vs stored): max |diff| = {parity:.3e}")
    if not parity < 1e-6:
        raise RuntimeError("Recomputed features do not match the supplied feature table; refusing to forecast.")

    print(f"Refitting {selected} on all {len(model_df):,} rows with a known next-day target ...")
    model = make_model(selected)
    if model is not None:
        model.fit(model_df[all_cols], model_df["target_next_day_demand"])
    dtypes = model_df[all_cols].dtypes.to_dict()

    os.makedirs(os.path.dirname(ARTIFACT_PATH), exist_ok=True)
    joblib.dump({"model": model, "model_name": selected, "feature_columns": all_cols, "dummy_columns": dummy_cols,
                 "dtypes": dtypes, "categories": categories, "trained_through_date": str(trained_through.date()),
                 "training_rows": int(len(model_df)), "hyperparameters": HYPERPARAMETERS.get(selected, {})},
                ARTIFACT_PATH)

    rows, clipped = forecast_all(model, selected, history, categories, all_cols, dtypes, horizon)
    basis = (f"Lowest RMSE in imported medicine_model_comparison ({selected}, RMSE={imported[selected]['rmse']:.4f}); "
             f"same features/hyperparameters as the supplied pipeline, refit on all history through "
             f"{trained_through.date()}.")
    notes = (f"Recursive {horizon}-step forecast; steps after the first use earlier predictions as inputs, so error "
             f"compounds with horizon. {clipped} negative prediction(s) clipped to 0. Does not model future stock receipts.")
    repro_json = {"models": repro, "feature_parity_max_abs_diff": parity}

    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO medicine_forecast_runs (model_name, trained_through_date, training_rows, horizon_days, "
            "hyperparameters, selection_basis, reproduction_check, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (selected, trained_through.date(), int(len(model_df)), horizon,
             json.dumps(HYPERPARAMETERS.get(selected, {})), basis, json.dumps(repro_json), notes))
        run_id = cur.lastrowid
        cur.executemany(
            "INSERT INTO medicine_forecasts (run_id, medicine_id, origin_date, forecast_date, horizon_step, "
            "uses_predicted_inputs, predicted_demand) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(run_id, *r) for r in rows])
    print(f"Saved run_id={run_id}: {len(rows)} forecast rows "
          f"({rows[0][2]} -> {rows[-1][2]}), artifact at {ARTIFACT_PATH}")
    return {"run_id": run_id, "rows": len(rows), "model_name": selected, "clipped": clipped}


def load_artifact():
    return joblib.load(ARTIFACT_PATH)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Medicine demand model utilities")
    ap.add_argument("command", choices=["train"])
    ap.add_argument("--horizon", type=int, default=None)
    args = ap.parse_args()
    from app.config import get_settings
    train(args.horizon or get_settings().forecast_horizon_days)
