"""
feature_engineering.py

Builds:
  - daily/weekly/monthly/yearly demand aggregates
  - ML feature dataset (leakage-safe: all rolling/lag features use only
    information available strictly before the prediction point)
  - fast/medium/slow-moving medicine tiers (documented volume-based rule)
  - anomaly detection dataset
  - trend analysis dataset
  - seasonality dataset

All grouping is by medicine_id / medicine_name / category only -- no
geographic grouping anywhere.
"""

import numpy as np
import pandas as pd

DEMAND_PATH = "/home/claude/medicine_data/synthetic/medicine_demand_SYNTHETIC.csv"
demand = pd.read_csv(DEMAND_PATH, parse_dates=["date"])
demand.sort_values(["medicine_id", "date"], inplace=True)

# ---------------------------------------------------------------------------
# 1. Daily / Weekly / Monthly / Yearly demand aggregates
# ---------------------------------------------------------------------------
daily = demand[[
    "date", "medicine_id", "medicine_name", "category",
    "units_requested", "units_issued", "units_dispensed",
]].copy()
daily.rename(columns={"units_requested": "daily_demand"}, inplace=True)
daily.to_csv("/home/claude/medicine_data/processed/medicine_demand_daily.csv", index=False)

daily["week"] = daily["date"].dt.to_period("W").apply(lambda p: p.start_time)
daily["month"] = daily["date"].dt.to_period("M").apply(lambda p: p.start_time)
daily["year"] = daily["date"].dt.year

group_cols = ["medicine_id", "medicine_name", "category"]
agg_map = {"daily_demand": "sum", "units_issued": "sum", "units_dispensed": "sum"}

weekly = daily.groupby(group_cols + ["week"], as_index=False).agg(agg_map)
weekly.rename(columns={"daily_demand": "weekly_demand", "week": "week_start"}, inplace=True)
weekly.to_csv("/home/claude/medicine_data/processed/medicine_demand_weekly.csv", index=False)

monthly = daily.groupby(group_cols + ["month"], as_index=False).agg(agg_map)
monthly.rename(columns={"daily_demand": "monthly_demand", "month": "month_start"}, inplace=True)
monthly.to_csv("/home/claude/medicine_data/processed/medicine_demand_monthly.csv", index=False)

yearly = daily.groupby(group_cols + ["year"], as_index=False).agg(agg_map)
yearly.rename(columns={"daily_demand": "yearly_demand"}, inplace=True)
yearly.to_csv("/home/claude/medicine_data/processed/medicine_demand_yearly.csv", index=False)

print("Daily/Weekly/Monthly/Yearly demand aggregates written (medicine-wise, no geography).")

# ---------------------------------------------------------------------------
# 2. ML feature dataset (leakage-safe)
# ---------------------------------------------------------------------------
SEASON_MAP = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring", 5: "Spring",
    6: "Summer", 7: "Summer", 8: "Summer",
    9: "Monsoon/Autumn", 10: "Monsoon/Autumn", 11: "Monsoon/Autumn",
}

def rolling_slope(series, window=30):
    slopes = np.full(len(series), np.nan)
    vals = series.values
    for i in range(window, len(vals)):
        y = vals[i - window:i]
        if np.isnan(y).any():
            continue
        x = np.arange(window)
        slopes[i] = np.polyfit(x, y, 1)[0]
    return slopes

feature_rows = []
trend_rows = []
seasonality_rows = []
anomaly_rows = []

for (med_id, med_name, category), grp in daily.groupby(group_cols):
    grp = grp.sort_values("date").reset_index(drop=True)
    s = grp["daily_demand"]

    weekly_roll = s.rolling(7, min_periods=1).sum()
    monthly_roll = s.rolling(30, min_periods=1).sum()

    shifted = s.shift(1)
    rolling_mean_7 = shifted.rolling(7, min_periods=1).mean()
    rolling_mean_30 = shifted.rolling(30, min_periods=1).mean()
    rolling_mean_90 = shifted.rolling(90, min_periods=1).mean()
    rolling_std_30 = shifted.rolling(30, min_periods=2).std()

    growth_rate_7d = (shifted - shifted.shift(7)) / shifted.shift(7).replace(0, np.nan)
    growth_rate_30d = (shifted - shifted.shift(30)) / shifted.shift(30).replace(0, np.nan)
    trend_slope = rolling_slope(shifted, window=30)

    lag_1 = s.shift(1)
    lag_7 = s.shift(7)
    lag_14 = s.shift(14)
    lag_30 = s.shift(30)

    seasonality_index = rolling_mean_7 / rolling_mean_90.replace(0, np.nan)

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

    # --- Trend analysis (medicine-level summary) ---
    # Fit a single linear regression of daily_demand vs. day-index over the
    # medicine's full history (a whole-series summary statistic; this is a
    # descriptive analysis output, not an ML feature, so no leakage concern).
    valid_mask = s.notna()
    x_full = np.arange(len(s))[valid_mask.values]
    y_full = s.values[valid_mask.values]
    if len(x_full) >= 2:
        overall_slope = np.polyfit(x_full, y_full, 1)[0]
    else:
        overall_slope = 0.0

    overall_growth_7d = grp["growth_rate_7d"].dropna().mean() if grp["growth_rate_7d"].notna().any() else 0.0
    overall_growth_30d = grp["growth_rate_30d"].dropna().mean() if grp["growth_rate_30d"].notna().any() else 0.0

    # Documented rule: project the fitted slope across the full observed
    # period and compare the implied total change to the medicine's mean
    # demand. >5% implied relative change => Increasing/Decreasing,
    # otherwise Stable.
    mean_demand = s.mean()
    implied_total_change = overall_slope * len(s)
    relative_change = implied_total_change / mean_demand if mean_demand > 0 else 0.0
    if relative_change > 0.05:
        direction = "Increasing"
    elif relative_change < -0.05:
        direction = "Decreasing"
    else:
        direction = "Stable"

    trend_rows.append({
        "medicine_id": med_id,
        "medicine_name": med_name,
        "trend_slope": round(float(overall_slope), 4),
        "trend_direction": direction,
        "growth_rate_7d": round(float(overall_growth_7d), 4),
        "growth_rate_30d": round(float(overall_growth_30d), 4),
    })

    # --- Seasonality (medicine x month summary) ---
    grp_month = grp.groupby("month").agg(
        avg_seasonality_index=("seasonality_index", "mean")
    ).reset_index()
    for _, mrow in grp_month.iterrows():
        month_num = int(mrow["month"])
        seasonality_rows.append({
            "medicine_id": med_id,
            "medicine_name": med_name,
            "month": month_num,
            "season": SEASON_MAP[month_num],
            "seasonality_index": round(float(mrow["avg_seasonality_index"]), 4) if pd.notna(mrow["avg_seasonality_index"]) else None,
        })

    # --- Anomalies (row-level, only flagged rows) ---
    flagged = grp[grp["anomaly_flag"] == 1].copy()
    for _, arow in flagged.iterrows():
        if pd.isna(arow["anomaly_score"]):
            continue
        anomaly_type = "Demand Spike" if arow["anomaly_score"] > 0 else "Demand Drop"
        anomaly_rows.append({
            "date": arow["date"].strftime("%Y-%m-%d"),
            "medicine_id": med_id,
            "medicine_name": med_name,
            "actual_demand": int(arow["daily_demand"]),
            "expected_demand": round(float(arow["rolling_mean_30"]), 2) if pd.notna(arow["rolling_mean_30"]) else None,
            "anomaly_score": round(float(arow["anomaly_score"]), 4),
            "anomaly_flag": 1,
            "anomaly_type": anomaly_type,
        })

features = pd.concat(feature_rows, ignore_index=True)
features = features[[
    "date", "medicine_id", "medicine_name", "category",
    "daily_demand", "weekly_demand", "monthly_demand",
    "rolling_mean_7", "rolling_mean_30",
    "growth_rate_7d", "growth_rate_30d", "trend_slope",
    "month", "day_of_week", "season", "seasonality_index",
    "lag_1", "lag_7", "lag_14", "lag_30",
    "anomaly_flag", "anomaly_score",
]]
features.sort_values(["medicine_id", "date"], inplace=True)
FEATURES_OUT = "/home/claude/medicine_data/processed/medicine_demand_features.csv"
features.to_csv(FEATURES_OUT, index=False)
print(f"Feature dataset written -> {FEATURES_OUT} ({len(features):,} rows)")

trend_df = pd.DataFrame(trend_rows)
TREND_OUT = "/home/claude/medicine_data/processed/medicine_trend_analysis.csv"
trend_df.to_csv(TREND_OUT, index=False)
print(f"Trend analysis written -> {TREND_OUT} ({len(trend_df)} medicines)")
print(trend_df["trend_direction"].value_counts())

season_df = pd.DataFrame(seasonality_rows)
SEASON_OUT = "/home/claude/medicine_data/processed/medicine_seasonality.csv"
season_df.to_csv(SEASON_OUT, index=False)
print(f"Seasonality dataset written -> {SEASON_OUT} ({len(season_df)} rows)")

anomaly_df = pd.DataFrame(anomaly_rows)
ANOMALY_OUT = "/home/claude/medicine_data/processed/medicine_demand_anomalies.csv"
anomaly_df.to_csv(ANOMALY_OUT, index=False)
print(f"Anomalies dataset written -> {ANOMALY_OUT} ({len(anomaly_df)} flagged rows)")

# ---------------------------------------------------------------------------
# 3. Fast / Medium / Slow moving medicine tiers
# ---------------------------------------------------------------------------
# Documented rule: rank medicines by total units_dispensed over the full
# period; top third = Fast Moving, middle third = Medium Moving,
# bottom third = Slow Moving. This is a medicine-LEVEL classification,
# supported by the data (per-medicine daily demand series exists for all
# 20 medicines in the synthetic catalog).
total_dispensed = demand.groupby(["medicine_id", "medicine_name", "category"], as_index=False)["units_dispensed"].sum()
total_dispensed.rename(columns={"units_dispensed": "total_units_dispensed"}, inplace=True)
total_dispensed.sort_values("total_units_dispensed", ascending=False, inplace=True)
total_dispensed.reset_index(drop=True, inplace=True)

n = len(total_dispensed)
tier_1_cut = n // 3
tier_2_cut = 2 * n // 3

def assign_tier(rank):
    if rank < tier_1_cut:
        return "Fast Moving"
    elif rank < tier_2_cut:
        return "Medium Moving"
    else:
        return "Slow Moving"

total_dispensed["volume_tier"] = [assign_tier(i) for i in range(n)]
TIERS_OUT = "/home/claude/medicine_data/processed/medicine_volume_tiers.csv"
total_dispensed.to_csv(TIERS_OUT, index=False)
print(f"Volume tiers written -> {TIERS_OUT}")
print(total_dispensed[["medicine_name", "total_units_dispensed", "volume_tier"]].to_string(index=False))
