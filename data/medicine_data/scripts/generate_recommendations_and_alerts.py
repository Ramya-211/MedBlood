"""
generate_recommendations_and_alerts.py

Generates medicine_recommendations_SYNTHETIC.csv and
medicine_alerts_SYNTHETIC.csv from ACTUAL calculated conditions:
  - predicted demand vs latest available stock
  - stock_status (from inventory dataset, threshold-based)
  - demand trend (from trend analysis dataset)
  - anomaly_flag (from latest feature row)
  - batch expiry_status (from batches dataset)
"""

import pandas as pd
import numpy as np

BASE = "/home/claude/medicine_data"

inv = pd.read_csv(f"{BASE}/synthetic/medicine_inventory_SYNTHETIC.csv", parse_dates=["date"])
features = pd.read_csv(f"{BASE}/processed/medicine_demand_features.csv", parse_dates=["date"])
avp = pd.read_csv(f"{BASE}/ml/medicine_actual_vs_predicted.csv", parse_dates=["date"])
trend = pd.read_csv(f"{BASE}/processed/medicine_trend_analysis.csv")
batches = pd.read_csv(f"{BASE}/synthetic/medicine_batches_SYNTHETIC.csv")

latest_date = inv["date"].max()
latest_stock = inv[inv["date"] == latest_date][["medicine_id", "medicine_name", "closing_stock", "stock_status"]].rename(
    columns={"closing_stock": "current_stock"}
)

latest_pred_date = avp["date"].max()
latest_pred = avp[avp["date"] == latest_pred_date][["medicine_id", "predicted_demand"]]

latest_feat_date = features["date"].max()
latest_feat = features[features["date"] == latest_feat_date][["medicine_id", "anomaly_flag"]]

batch_status = batches.groupby("medicine_id")["expiry_status"].apply(
    lambda s: "Expired" if (s == "Expired").any() else ("Near Expiry" if (s == "Near Expiry").any() else "Safe")
).reset_index().rename(columns={"expiry_status": "med_expiry_status"})

merged = latest_stock.merge(latest_pred, on="medicine_id", how="left")
merged = merged.merge(latest_feat, on="medicine_id", how="left")
merged = merged.merge(trend[["medicine_id", "trend_direction", "growth_rate_7d"]], on="medicine_id", how="left")
merged = merged.merge(batch_status, on="medicine_id", how="left")
merged["med_expiry_status"] = merged["med_expiry_status"].fillna("Safe")
merged["anomaly_flag"] = merged["anomaly_flag"].fillna(0)

recommendations = []
rec_id = 1
for _, row in merged.iterrows():
    entries = []  # (type, severity, reason, action)

    if pd.notna(row["predicted_demand"]) and row["predicted_demand"] > row["current_stock"]:
        entries.append((
            "Potential Shortage", "Warning",
            f"Predicted demand ({row['predicted_demand']:.1f}) exceeds current stock ({row['current_stock']}).",
            "Review Replenishment",
        ))
    if row["stock_status"] == "Critical":
        entries.append((
            "Critical Stock", "Critical",
            f"Current stock ({row['current_stock']}) is critically low per days-of-cover threshold.",
            "Immediate Replenishment",
        ))
    elif row["stock_status"] == "Low":
        entries.append((
            "Low Stock", "Warning",
            f"Current stock ({row['current_stock']}) is below the low-stock threshold.",
            "Review Replenishment",
        ))
    elif row["stock_status"] == "Overstock":
        entries.append((
            "Excess Stock", "Info",
            f"Current stock ({row['current_stock']}) exceeds the overstock threshold (days of cover).",
            "Review Excess Inventory",
        ))
    if row["trend_direction"] == "Increasing" and pd.notna(row["growth_rate_7d"]) and row["growth_rate_7d"] > 0.10:
        entries.append((
            "Demand Increasing", "Info",
            f"7-day growth rate averages {row['growth_rate_7d']:.2%}; demand trend is Increasing.",
            "Prepare Inventory Review",
        ))
    elif row["trend_direction"] == "Decreasing":
        entries.append((
            "Demand Decreasing", "Info",
            "Demand trend is Decreasing based on full-history linear fit.",
            "Monitor for Overstock Risk",
        ))
    if row["anomaly_flag"] == 1:
        entries.append((
            "Demand Anomaly", "Warning",
            "Latest daily demand deviates more than 2.5 standard deviations from its 30-day rolling mean.",
            "Review Recent Demand Pattern",
        ))
    if row["med_expiry_status"] in ("Near Expiry", "Expired"):
        entries.append((
            "Expiry Priority", "Warning" if row["med_expiry_status"] == "Near Expiry" else "Critical",
            f"One or more batches are {row['med_expiry_status']}.",
            "Prioritize Stock Utilization (FIFO)",
        ))

    if not entries:
        entries.append((
            "Normal Monitoring", "Info",
            "Stock, demand trend, and expiry status are within normal parameters.",
            "No Action Needed",
        ))

    for rec_type, severity, reason, action in entries:
        recommendations.append({
            "recommendation_id": rec_id,
            "date": latest_date.strftime("%Y-%m-%d"),
            "medicine_id": row["medicine_id"],
            "medicine_name": row["medicine_name"],
            "recommendation_type": rec_type,
            "severity": severity,
            "reason": reason,
            "recommended_action": action,
        })
        rec_id += 1

rec_df = pd.DataFrame(recommendations)
REC_OUT = f"{BASE}/recommendations/medicine_recommendations_SYNTHETIC.csv"
rec_df.to_csv(REC_OUT, index=False)
print(f"Generated {len(rec_df):,} recommendation rows -> {REC_OUT}")

# ---------------------------------------------------------------------------
# Alerts: subset of recommendation types mapped to formal alert vocabulary
# ---------------------------------------------------------------------------
ALERT_TYPE_MAP = {
    "Low Stock": "Low Stock",
    "Critical Stock": "Critical Stock",
    "Potential Shortage": "Potential Shortage",
    "Excess Stock": "Overstock",
    "Demand Anomaly": "Anomaly",
    "Expiry Priority": None,  # handled specially below (Near Expiry / Expired)
    "Demand Increasing": "Increasing Demand",
}

alerts = []
alert_id = 1
for _, row in rec_df.iterrows():
    rtype = row["recommendation_type"]
    if rtype == "Normal Monitoring" or rtype == "Demand Decreasing":
        continue
    if rtype == "Expiry Priority":
        seg_status = merged[merged["medicine_id"] == row["medicine_id"]]["med_expiry_status"].iloc[0]
        alert_type = "Expired" if seg_status == "Expired" else "Near Expiry"
        severity = "Critical" if alert_type == "Expired" else "Warning"
    else:
        alert_type = ALERT_TYPE_MAP.get(rtype)
        if alert_type is None:
            continue
        severity = row["severity"]

    message = f"{alert_type} - {row['medicine_name']}: {row['reason']}"
    alerts.append({
        "alert_id": alert_id,
        "date": row["date"],
        "medicine_id": row["medicine_id"],
        "medicine_name": row["medicine_name"],
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
    })
    alert_id += 1

alerts_df = pd.DataFrame(alerts)
ALERTS_OUT = f"{BASE}/alerts/medicine_alerts_SYNTHETIC.csv"
alerts_df.to_csv(ALERTS_OUT, index=False)
print(f"Generated {len(alerts_df):,} alert rows -> {ALERTS_OUT}")
