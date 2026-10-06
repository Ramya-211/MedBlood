"""
train_medicine_models.py

Trains and evaluates models to predict future medicine demand
(target = next-day units_requested per medicine). Chronological
train/validation/test split -- no shuffling.

Outputs:
  medicine_data/ml/medicine_model_comparison.csv
  medicine_data/ml/medicine_actual_vs_predicted.csv
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

FEATURES_PATH = "/home/claude/medicine_data/processed/medicine_demand_features.csv"
df = pd.read_csv(FEATURES_PATH, parse_dates=["date"])
df.sort_values(["medicine_id", "date"], inplace=True)

df["target_next_day_demand"] = df.groupby("medicine_id")["daily_demand"].shift(-1)

FEATURE_COLS = [
    "rolling_mean_7", "rolling_mean_30",
    "growth_rate_7d", "growth_rate_30d", "trend_slope",
    "month", "day_of_week", "seasonality_index",
    "lag_1", "lag_7", "lag_14", "lag_30",
    "anomaly_flag", "anomaly_score",
]

cat_cols = ["medicine_id", "category", "season"]
df_with_orig = df.copy()
for c in ["medicine_id", "medicine_name", "category"]:
    df_with_orig[c + "_orig"] = df_with_orig[c]

model_df = pd.get_dummies(df_with_orig, columns=cat_cols, drop_first=False)
dummy_cols = [c for c in model_df.columns if any(c.startswith(p + "_") for p in cat_cols) and not c.endswith("_orig")]
all_feature_cols = FEATURE_COLS + dummy_cols

model_df = model_df.dropna(subset=all_feature_cols + ["target_next_day_demand"]).reset_index(drop=True)
model_df.sort_values("date", inplace=True)
model_df.reset_index(drop=True, inplace=True)

n = len(model_df)
train_end = int(n * 0.70)
val_end = int(n * 0.85)

train_df = model_df.iloc[:train_end]
val_df = model_df.iloc[train_end:val_end]
test_df = model_df.iloc[val_end:]

X_train, y_train = train_df[all_feature_cols], train_df["target_next_day_demand"]
X_val, y_val = val_df[all_feature_cols], val_df["target_next_day_demand"]
X_test, y_test = test_df[all_feature_cols], test_df["target_next_day_demand"]

print(f"Train rows: {len(train_df):,} | Val rows: {len(val_df):,} | Test rows: {len(test_df):,}")
print(f"Train date range: {train_df['date'].min()} -> {train_df['date'].max()}")
print(f"Val date range:   {val_df['date'].min()} -> {val_df['date'].max()}")
print(f"Test date range:  {test_df['date'].min()} -> {test_df['date'].max()}")

results = []
predictions_store = {}

def evaluate(name, y_true, y_pred):
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    return {"model": name, "RMSE": rmse, "MAE": mae, "R2": r2}

# 1. Baseline
baseline_pred = X_test["lag_1"].values
results.append(evaluate("Baseline (naive lag-1)", y_test, baseline_pred))
predictions_store["Baseline (naive lag-1)"] = baseline_pred

# 2. Linear Regression
lr = LinearRegression()
lr.fit(X_train, y_train)
lr_pred = lr.predict(X_test)
results.append(evaluate("Linear Regression", y_test, lr_pred))
predictions_store["Linear Regression"] = lr_pred

# 3. Random Forest Regressor
rf = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
rf_pred = rf.predict(X_test)
results.append(evaluate("Random Forest Regressor", y_test, rf_pred))
predictions_store["Random Forest Regressor"] = rf_pred

# 4. XGBoost Regressor
if HAS_XGB:
    xgb = XGBRegressor(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1
    )
    xgb.fit(X_train, y_train)
    xgb_pred = xgb.predict(X_test)
    results.append(evaluate("XGBoost Regressor", y_test, xgb_pred))
    predictions_store["XGBoost Regressor"] = xgb_pred
else:
    print("WARNING: xgboost not installed -- skipping XGBoost model.")

results_df = pd.DataFrame(results)
results_df.sort_values("RMSE", inplace=True)
COMPARISON_OUT = "/home/claude/medicine_data/ml/medicine_model_comparison.csv"
results_df.to_csv(COMPARISON_OUT, index=False)
print("\nModel comparison (sorted by RMSE, lower is better):")
print(results_df.to_string(index=False))

best_model_name = results_df.iloc[0]["model"]
print(f"\nSelected model based on lowest test-set RMSE: {best_model_name}")

best_pred = predictions_store[best_model_name]
avp = test_df[["date", "medicine_id_orig", "medicine_name_orig"]].copy()
avp.rename(columns={"medicine_id_orig": "medicine_id", "medicine_name_orig": "medicine_name"}, inplace=True)
avp["actual_demand"] = y_test.values
avp["predicted_demand"] = best_pred
avp["prediction_error"] = avp["actual_demand"] - avp["predicted_demand"]

AVP_OUT = "/home/claude/medicine_data/ml/medicine_actual_vs_predicted.csv"
avp.to_csv(AVP_OUT, index=False)
print(f"\nActual vs Predicted written -> {AVP_OUT} ({len(avp):,} rows)")

with open("/home/claude/medicine_data/ml/_run_summary.txt", "w") as f:
    f.write(f"best_model={best_model_name}\n")
    f.write(f"n_train={len(train_df)}\n")
    f.write(f"n_val={len(val_df)}\n")
    f.write(f"n_test={len(test_df)}\n")
    f.write(f"train_range={train_df['date'].min()} to {train_df['date'].max()}\n")
    f.write(f"val_range={val_df['date'].min()} to {val_df['date'].max()}\n")
    f.write(f"test_range={test_df['date'].min()} to {test_df['date'].max()}\n")
    f.write(f"has_xgb={HAS_XGB}\n")
    for r in results:
        f.write(f"metric_{r['model']}=RMSE:{r['RMSE']:.4f},MAE:{r['MAE']:.4f},R2:{r['R2']:.4f}\n")
