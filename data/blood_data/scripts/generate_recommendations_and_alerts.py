"""
generate_recommendations_and_alerts.py

Generates blood_recommendations_SYNTHETIC.csv and blood_alerts_SYNTHETIC.csv
from ACTUAL calculated conditions:
  - predicted demand vs latest available stock
  - stock level thresholds (Low/Critical/Normal/Overstock)
  - demand trend (growth_rate_7d)
  - anomaly_flag
  - batch expiry_status

Thresholds used (documented, not random):
  CRITICAL_STOCK_DAYS = stock covers < 2 days of avg daily issuance
  LOW_STOCK_DAYS      = stock covers < 5 days of avg daily issuance
  OVERSTOCK_DAYS      = stock covers > 30 days of avg daily issuance
"""

import numpy as np
import pandas as pd

INV_PATH = "/home/claude/blood_data/synthetic/blood_inventory_SYNTHETIC.csv"
FEATURES_PATH = "/home/claude/blood_data/processed/blood_demand_features_SYNTHETIC.csv"
AVP_PATH = "/home/claude/blood_data/ml/blood_demand_actual_vs_predicted.csv"
BATCH_PATH = "/home/claude/blood_data/synthetic/blood_batches_SYNTHETIC.csv"

inv = pd.read_csv(INV_PATH, parse_dates=["date"])
features = pd.read_csv(FEATURES_PATH, parse_dates=["date"])
avp = pd.read_csv(AVP_PATH, parse_dates=["date"])
batches = pd.read_csv(BATCH_PATH, parse_dates=["collection_date", "expiry_date"])

SEG_COLS = ["blood_group", "rh_type", "blood_component"]

# Latest closing stock per segment
latest_date = inv["date"].max()
latest_stock = inv[inv["date"] == latest_date][SEG_COLS + ["closing_stock"]].rename(
    columns={"closing_stock": "current_stock"}
)

# Average daily issuance per segment (last 30 days) to compute "days of cover"
recent_inv = inv[inv["date"] > latest_date - pd.Timedelta(days=30)]
avg_daily_issue = recent_inv.groupby(SEG_COLS, as_index=False)["units_issued"].mean().rename(
    columns={"units_issued": "avg_daily_issuance"}
)

status_df = latest_stock.merge(avg_daily_issue, on=SEG_COLS, how="left")
status_df["avg_daily_issuance"] = status_df["avg_daily_issuance"].replace(0, np.nan)
status_df["days_of_cover"] = status_df["current_stock"] / status_df["avg_daily_issuance"]
status_df["days_of_cover"] = status_df["days_of_cover"].fillna(0)

CRITICAL_DAYS = 2
LOW_DAYS = 5
OVERSTOCK_DAYS = 30

def stock_status(days):
    if days < CRITICAL_DAYS:
        return "Critical"
    elif days < LOW_DAYS:
        return "Low"
    elif days > OVERSTOCK_DAYS:
        return "Overstock"
    else:
        return "Normal"

status_df["stock_status"] = status_df["days_of_cover"].apply(stock_status)

# Latest predicted demand (from actual vs predicted, most recent date per segment)
latest_pred_date = avp["date"].max()
latest_pred = avp[avp["date"] == latest_pred_date][SEG_COLS + ["predicted_demand"]]

# Latest demand trend and anomaly flag (from features, most recent date per segment)
latest_feat_date = features["date"].max()
latest_feat = features[features["date"] == latest_feat_date][
    SEG_COLS + ["growth_rate_7d", "anomaly_flag"]
]

merged = status_df.merge(latest_pred, on=SEG_COLS, how="left")
merged = merged.merge(latest_feat, on=SEG_COLS, how="left")

# Near-expiry / expired batch presence per segment
batch_status = batches.groupby(SEG_COLS)["expiry_status"].apply(
    lambda s: "Expired" if (s == "Expired").any() else ("Near Expiry" if (s == "Near Expiry").any() else "Safe")
).reset_index().rename(columns={"expiry_status": "segment_expiry_status"})

merged = merged.merge(batch_status, on=SEG_COLS, how="left")
merged["segment_expiry_status"] = merged["segment_expiry_status"].fillna("Safe")

# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
recommendations = []
rec_id = 1
for _, row in merged.iterrows():
    recs = []
    if pd.notna(row["predicted_demand"]) and row["predicted_demand"] > row["current_stock"]:
        recs.append("Potential Shortage / Review Replenishment")
    if row["stock_status"] == "Low":
        recs.append("Low Stock Alert - Consider Replenishment")
    if row["stock_status"] == "Critical":
        recs.append("Critical Stock Alert - Immediate Replenishment Needed")
    if pd.notna(row["growth_rate_7d"]) and row["growth_rate_7d"] > 0.15:
        recs.append("Prepare for Increased Requirement (Rising Demand Trend)")
    if row["anomaly_flag"] == 1:
        recs.append("Review Unusual Demand (Anomaly Detected)")
    if row["segment_expiry_status"] in ("Near Expiry", "Expired"):
        recs.append("Expiry Priority - Prioritize Issuance of Near-Expiry Units")
    if row["stock_status"] == "Overstock":
        recs.append("Review Excess Inventory")

    if not recs:
        recs.append("No Action Needed - Stock and Demand Within Normal Range")

    for r in recs:
        recommendations.append({
            "recommendation_id": rec_id,
            "date": latest_date.strftime("%Y-%m-%d"),
            "blood_group": row["blood_group"],
            "rh_type": row["rh_type"],
            "blood_component": row["blood_component"],
            "current_stock": int(row["current_stock"]),
            "predicted_demand": None if pd.isna(row["predicted_demand"]) else round(float(row["predicted_demand"]), 2),
            "days_of_cover": round(float(row["days_of_cover"]), 2),
            "recommendation": r,
        })
        rec_id += 1

rec_df = pd.DataFrame(recommendations)
REC_OUT = "/home/claude/blood_data/recommendations/blood_recommendations_SYNTHETIC.csv"
rec_df.to_csv(REC_OUT, index=False)
print(f"Generated {len(rec_df):,} recommendation rows -> {REC_OUT}")

# ---------------------------------------------------------------------------
# Alerts (subset of recommendations mapped to formal alert types/severity)
# ---------------------------------------------------------------------------
ALERT_MAP = {
    "Low Stock Alert - Consider Replenishment": ("Low Stock", "Warning"),
    "Critical Stock Alert - Immediate Replenishment Needed": ("Critical Stock", "Critical"),
    "Potential Shortage / Review Replenishment": ("Potential Shortage", "Warning"),
    "Prepare for Increased Requirement (Rising Demand Trend)": ("Increasing Demand", "Info"),
    "Review Unusual Demand (Anomaly Detected)": ("Demand Anomaly", "Warning"),
    "Expiry Priority - Prioritize Issuance of Near-Expiry Units": ("Near Expiry", "Warning"),
    "Review Excess Inventory": ("Excess Stock", "Info"),
}

alerts = []
alert_id = 1
for _, row in rec_df.iterrows():
    if row["recommendation"] in ALERT_MAP:
        alert_type, severity = ALERT_MAP[row["recommendation"]]
        # Escalate Near Expiry -> Expired if applicable
        if alert_type == "Near Expiry":
            seg_status = merged[
                (merged["blood_group"] == row["blood_group"]) &
                (merged["rh_type"] == row["rh_type"]) &
                (merged["blood_component"] == row["blood_component"])
            ]["segment_expiry_status"].iloc[0]
            if seg_status == "Expired":
                alert_type, severity = "Expired", "Critical"

        message = (
            f"{alert_type} for {row['blood_group']}{'+' if row['rh_type']=='Positive' else '-'} "
            f"{row['blood_component']}: current stock {row['current_stock']} units, "
            f"days of cover {row['days_of_cover']:.1f}."
        )
        alerts.append({
            "alert_id": alert_id,
            "date": row["date"],
            "blood_group": row["blood_group"],
            "rh_type": row["rh_type"],
            "blood_component": row["blood_component"],
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
        })
        alert_id += 1

alerts_df = pd.DataFrame(alerts)
ALERTS_OUT = "/home/claude/blood_data/alerts/blood_alerts_SYNTHETIC.csv"
alerts_df.to_csv(ALERTS_OUT, index=False)
print(f"Generated {len(alerts_df):,} alert rows -> {ALERTS_OUT}")
