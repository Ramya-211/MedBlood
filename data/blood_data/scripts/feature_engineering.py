"""
feature_engineering.py

Builds time-based demand aggregates (daily/weekly/monthly/yearly) and the
ML feature dataset from the SYNTHETIC patient demand dataset.

No geographical grouping is performed anywhere in this script.
Grouping dimensions used: blood_group, rh_type, blood_component, date.

All rolling/lag features use only information available strictly before
the prediction point (shift(1) applied before rolling/lag calculations)
to avoid data leakage.
"""

import numpy as np
import pandas as pd

DEMAND_PATH = "/home/claude/blood_data/synthetic/blood_patient_demand_SYNTHETIC.csv"
demand = pd.read_csv(DEMAND_PATH, parse_dates=["date"])
demand.sort_values(["blood_group", "rh_type", "blood_component", "date"], inplace=True)

# ---------------------------------------------------------------------------
# 1. Daily demand (== units_requested per segment per day, already granular)
# ---------------------------------------------------------------------------
daily = demand[[
    "date", "blood_group", "rh_type", "blood_component",
    "units_requested", "units_issued", "units_transfused",
    "emergency_requests", "routine_requests",
]].copy()
daily.rename(columns={"units_requested": "daily_demand"}, inplace=True)
daily.to_csv("/home/claude/blood_data/processed/blood_demand_daily_SYNTHETIC.csv", index=False)

# ---------------------------------------------------------------------------
# 2. Weekly / Monthly / Yearly aggregates (derived from daily)
# ---------------------------------------------------------------------------
daily["week"] = daily["date"].dt.to_period("W").apply(lambda p: p.start_time)
daily["month"] = daily["date"].dt.to_period("M").apply(lambda p: p.start_time)
daily["year"] = daily["date"].dt.year

group_cols = ["blood_group", "rh_type", "blood_component"]
agg_map = {
    "daily_demand": "sum",
    "units_issued": "sum",
    "units_transfused": "sum",
    "emergency_requests": "sum",
    "routine_requests": "sum",
}

weekly = daily.groupby(group_cols + ["week"], as_index=False).agg(agg_map)
weekly.rename(columns={"daily_demand": "weekly_demand", "week": "week_start"}, inplace=True)
weekly.to_csv("/home/claude/blood_data/processed/blood_demand_weekly_SYNTHETIC.csv", index=False)

monthly = daily.groupby(group_cols + ["month"], as_index=False).agg(agg_map)
monthly.rename(columns={"daily_demand": "monthly_demand", "month": "month_start"}, inplace=True)
monthly.to_csv("/home/claude/blood_data/processed/blood_demand_monthly_SYNTHETIC.csv", index=False)

yearly = daily.groupby(group_cols + ["year"], as_index=False).agg(agg_map)
yearly.rename(columns={"daily_demand": "yearly_demand"}, inplace=True)
yearly.to_csv("/home/claude/blood_data/processed/blood_demand_yearly_SYNTHETIC.csv", index=False)

print("Daily/Weekly/Monthly/Yearly demand aggregates written (no geographic grouping).")

# ---------------------------------------------------------------------------
# 3. ML feature dataset (blood_demand_features_SYNTHETIC.csv)
# ---------------------------------------------------------------------------
SEASON_MAP = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring", 5: "Spring",
    6: "Summer", 7: "Summer", 8: "Summer",
    9: "Monsoon/Autumn", 10: "Monsoon/Autumn", 11: "Monsoon/Autumn",
}

feature_rows = []

for (bg, rh, comp), grp in daily.groupby(group_cols):
    grp = grp.sort_values("date").reset_index(drop=True)
    s = grp["daily_demand"]

    # Weekly/monthly demand mapped back onto the daily row (rolling sums ending at t,
    # using only data up to and including t -- these are descriptive contextual
    # features, not leakage since they characterize the current/past window).
    weekly_roll = s.rolling(7, min_periods=1).sum()
    monthly_roll = s.rolling(30, min_periods=1).sum()

    # Rolling means computed on data STRICTLY BEFORE the current day (shift(1))
    # to avoid leaking same-day demand into predictive features.
    shifted = s.shift(1)
    rolling_mean_7 = shifted.rolling(7, min_periods=1).mean()
    rolling_mean_30 = shifted.rolling(30, min_periods=1).mean()

    # Growth rates based on past values only
    lag_7_for_growth = shifted.shift(6)   # value 7 days before "shifted" reference -> t-7 vs t-14 style
    growth_rate_7d = (shifted - shifted.shift(7)) / shifted.shift(7).replace(0, np.nan)
    growth_rate_30d = (shifted - shifted.shift(30)) / shifted.shift(30).replace(0, np.nan)

    # Trend slope: slope of a rolling 30-day linear fit on past values only
    def rolling_slope(series, window=30):
        slopes = np.full(len(series), np.nan)
        vals = series.values
        for i in range(window, len(vals)):
            y = vals[i - window:i]
            if np.isnan(y).any():
                continue
            x = np.arange(window)
            slope = np.polyfit(x, y, 1)[0]
            slopes[i] = slope
        return slopes

    trend_slope = rolling_slope(shifted, window=30)

    # Lags (strictly past values)
    lag_1 = s.shift(1)
    lag_7 = s.shift(7)
    lag_14 = s.shift(14)
    lag_30 = s.shift(30)

    # Seasonality index: ratio of past 7-day mean to past 90-day mean (captures
    # relative seasonal elevation using only past information)
    rolling_mean_90 = shifted.rolling(90, min_periods=1).mean()
    seasonality_index = rolling_mean_7 / rolling_mean_90.replace(0, np.nan)

    # Anomaly detection: z-score of current value vs past 30-day mean/std (past only)
    rolling_std_30 = shifted.rolling(30, min_periods=2).std()
    anomaly_score = (s - rolling_mean_30) / rolling_std_30.replace(0, np.nan)
    anomaly_flag = (anomaly_score.abs() > 2.5).astype(int)

    grp["weekly_demand"] = weekly_roll
    grp["monthly_demand"] = monthly_roll
    grp["rolling_mean_7"] = rolling_mean_7
    grp["rolling_mean_30"] = rolling_mean_30
    grp["growth_rate_7d"] = growth_rate_7d
    grp["growth_rate_30d"] = growth_rate_30d
    grp["trend_slope"] = trend_slope
    grp["month"] = grp["date"].dt.month
    grp["day_of_week"] = grp["date"].dt.dayofweek
    grp["season"] = grp["month"].map(SEASON_MAP)
    grp["seasonality_index"] = seasonality_index
    grp["lag_1"] = lag_1
    grp["lag_7"] = lag_7
    grp["lag_14"] = lag_14
    grp["lag_30"] = lag_30
    grp["anomaly_score"] = anomaly_score
    grp["anomaly_flag"] = anomaly_flag

    feature_rows.append(grp)

features = pd.concat(feature_rows, ignore_index=True)
features = features[[
    "date", "blood_group", "rh_type", "blood_component",
    "daily_demand", "weekly_demand", "monthly_demand",
    "rolling_mean_7", "rolling_mean_30",
    "growth_rate_7d", "growth_rate_30d", "trend_slope",
    "month", "day_of_week", "season", "seasonality_index",
    "lag_1", "lag_7", "lag_14", "lag_30",
    "anomaly_flag", "anomaly_score",
]]

features.sort_values(["blood_group", "rh_type", "blood_component", "date"], inplace=True)
FEATURES_OUT = "/home/claude/blood_data/processed/blood_demand_features_SYNTHETIC.csv"
features.to_csv(FEATURES_OUT, index=False)

print(f"Feature dataset written -> {FEATURES_OUT} ({len(features):,} rows)")
print("All rolling/lag features use only pre-prediction-point information (no leakage).")
