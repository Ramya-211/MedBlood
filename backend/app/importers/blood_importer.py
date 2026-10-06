"""
blood_importer.py

Imports the supplied (unmodified) blood_data/ CSV files into MySQL using
raw parameterized SQL via mysql-connector-python.

NOTE ON blood_recommendations_SYNTHETIC.csv:
The supplied file stores each recommendation as one free-text string
(column "recommendation") rather than split into
recommendation_type/severity/reason columns the way the medicine dataset
does. RECOMMENDATION_TEXT_MAP below is a deterministic, exhaustive mapping
from the ACTUAL distinct strings found in that column (verified during
Phase 1 inspection) to structured fields. This is a parsing/normalization
step, not fabrication -- no new information is introduced, the same text
is just split into columns matching the medicine schema for consistency.
If a future data refresh introduces a new, unmapped string, the importer
raises an error rather than silently guessing.

Run standalone:
    python3 -m app.importers.blood_importer
"""

import sys
import os
import math
import datetime
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.importers.import_db import get_import_connection

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.environ.get("BLOOD_DATA_DIR", os.path.join(PROJECT_ROOT, "data", "blood_data"))

RECOMMENDATION_TEXT_MAP = {
    "No Action Needed - Stock and Demand Within Normal Range": (
        "Normal Monitoring", "Info", "Stock and predicted demand are within normal parameters."),
    "Expiry Priority - Prioritize Issuance of Near-Expiry Units": (
        "Expiry Priority", "Warning", "One or more batches for this segment are Near Expiry or Expired."),
    "Low Stock Alert - Consider Replenishment": (
        "Low Stock", "Warning", "Current stock is below the low-stock days-of-cover threshold."),
    "Prepare for Increased Requirement (Rising Demand Trend)": (
        "Demand Increasing", "Info", "7-day demand growth rate indicates a rising trend."),
}


def nz(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    return v


def log_import(cursor, dataset_name, file_name, rows_read, rows_inserted, rows_rejected, started_at, notes=""):
    cursor.execute(
        """INSERT INTO import_log
           (dataset_name, file_name, rows_read, rows_inserted, rows_rejected, started_at, finished_at, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (dataset_name, file_name, rows_read, rows_inserted, rows_rejected,
         started_at, datetime.datetime.now(), notes),
    )


def import_blood_demand(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "blood_patient_demand_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    n_read = len(df)

    before = len(df)
    df = df[(df["emergency_requests"] + df["routine_requests"]) == df["units_requested"]]
    df = df[df["units_issued"] <= df["units_requested"]]
    df = df[df["units_transfused"] <= df["units_issued"]]
    rejected = before - len(df)

    cur = conn.cursor()
    rows = [
        (int(r.record_id), r.date.date(), r.blood_group, r.rh_type, r.blood_component,
         int(r.units_requested), int(r.units_issued), int(r.units_transfused),
         int(r.emergency_requests), int(r.routine_requests))
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO blood_demand
           (record_id, demand_date, blood_group, rh_type, blood_component, units_requested, units_issued,
            units_transfused, emergency_requests, routine_requests)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_patient_demand_SYNTHETIC.csv", n_read, len(rows), rejected, started)
    conn.commit()
    print(f"[blood_demand] inserted {len(rows)} rows, rejected {rejected}")


def import_blood_features(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "processed", "blood_demand_features_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = []
    for r in df.itertuples():
        rows.append((
            r.date.date(), r.blood_group, r.rh_type, r.blood_component,
            nz(r.daily_demand), nz(r.weekly_demand), nz(r.monthly_demand),
            nz(r.rolling_mean_7), nz(r.rolling_mean_30), nz(r.growth_rate_7d), nz(r.growth_rate_30d),
            nz(r.trend_slope), int(r.month), int(r.day_of_week), r.season, nz(r.seasonality_index),
            nz(r.lag_1), nz(r.lag_7), nz(r.lag_14), nz(r.lag_30), int(r.anomaly_flag), nz(r.anomaly_score),
        ))
    cur.executemany(
        """INSERT INTO blood_demand_features
           (feature_date, blood_group, rh_type, blood_component, daily_demand, weekly_demand, monthly_demand,
            rolling_mean_7, rolling_mean_30, growth_rate_7d, growth_rate_30d, trend_slope,
            month_num, day_of_week, season, seasonality_index, lag_1, lag_7, lag_14, lag_30,
            anomaly_flag, anomaly_score)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_demand_features_SYNTHETIC.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[blood_demand_features] inserted {len(rows)} rows")


def import_blood_collection(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "blood_collection_SYNTHETIC_placeholder.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (r.date.date(), r.blood_type, int(r.donation_volume), r.data_type)
        for r in df.itertuples()
    ]
    cur.executemany(
        "INSERT INTO blood_collection (collection_date, blood_type, donation_volume, data_type) VALUES (%s,%s,%s,%s)",
        rows,
    )
    log_import(cur, "blood", "blood_collection_SYNTHETIC_placeholder.csv", len(df), len(rows), 0, started,
               "SUPPLY-side placeholder; not real donation data (see BLOOD_DATA_REPORT.md)")
    conn.commit()
    print(f"[blood_collection] inserted {len(rows)} rows")


def import_blood_inventory(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "blood_inventory_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    n_read = len(df)

    before = len(df)
    calc = df["opening_stock"] + df["units_received"] - df["units_issued"] - df["units_discarded"] - df["units_expired"]
    df = df[calc == df["closing_stock"]]
    df = df[df["closing_stock"] >= 0]
    rejected = before - len(df)

    cur = conn.cursor()
    rows = [
        (int(r.inventory_id), r.date.date(), r.blood_group, r.rh_type, r.blood_component,
         int(r.opening_stock), int(r.units_received), int(r.units_issued),
         int(r.units_discarded), int(r.units_expired), int(r.closing_stock))
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO blood_inventory
           (inventory_id, inv_date, blood_group, rh_type, blood_component, opening_stock, units_received,
            units_issued, units_discarded, units_expired, closing_stock)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_inventory_SYNTHETIC.csv", n_read, len(rows), rejected, started)
    conn.commit()
    print(f"[blood_inventory] inserted {len(rows)} rows, rejected {rejected}")


def import_blood_batches(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "blood_batches_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["collection_date", "expiry_date"])
    cur = conn.cursor()
    rows = [
        (r.batch_id, r.collection_date.date(), r.expiry_date.date(), r.blood_group, r.rh_type,
         r.blood_component, int(r.units_in_batch), int(r.units_remaining), r.expiry_status)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO blood_batches
           (batch_id, collection_date, expiry_date, blood_group, rh_type, blood_component,
            units_in_batch, units_remaining, expiry_status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_batches_SYNTHETIC.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[blood_batches] inserted {len(rows)} rows")


def import_blood_alerts(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "alerts", "blood_alerts_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (int(r.alert_id), r.date.date(), r.blood_group, r.rh_type, r.blood_component,
         r.alert_type, r.severity, r.message)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO blood_alerts (alert_id, alert_date, blood_group, rh_type, blood_component, alert_type, severity, message)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_alerts_SYNTHETIC.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[blood_alerts] inserted {len(rows)} rows")


def import_blood_recommendations(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "recommendations", "blood_recommendations_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])

    unmapped = set(df["recommendation"].unique()) - set(RECOMMENDATION_TEXT_MAP.keys())
    if unmapped:
        raise ValueError(
            f"blood_recommendations_SYNTHETIC.csv contains recommendation text not covered by "
            f"RECOMMENDATION_TEXT_MAP: {unmapped}. Update the map before importing -- do not guess."
        )

    cur = conn.cursor()
    rows = []
    for r in df.itertuples():
        rec_type, severity, reason = RECOMMENDATION_TEXT_MAP[r.recommendation]
        rows.append((
            int(r.recommendation_id), r.date.date(), r.blood_group, r.rh_type, r.blood_component,
            int(r.current_stock), nz(r.predicted_demand), float(r.days_of_cover), rec_type, severity, reason,
        ))
    cur.executemany(
        """INSERT INTO blood_recommendations
           (recommendation_id, rec_date, blood_group, rh_type, blood_component, current_stock,
            predicted_demand, days_of_cover, recommendation_type, severity, reason)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_recommendations_SYNTHETIC.csv", len(df), len(rows), 0, started,
               "Free-text 'recommendation' column parsed into type/severity/reason via RECOMMENDATION_TEXT_MAP")
    conn.commit()
    print(f"[blood_recommendations] inserted {len(rows)} rows (parsed from free text)")


def import_blood_model_comparison(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "ml", "blood_model_comparison.csv")
    df = pd.read_csv(path)
    cur = conn.cursor()
    rows = [(r.model, float(r.RMSE), float(r.MAE), float(r.R2)) for r in df.itertuples()]
    cur.executemany(
        "INSERT INTO blood_model_comparison (model_name, rmse, mae, r2) VALUES (%s,%s,%s,%s)",
        rows,
    )
    log_import(cur, "blood", "blood_model_comparison.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[blood_model_comparison] inserted {len(rows)} rows")


def import_blood_avp(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "ml", "blood_demand_actual_vs_predicted.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (r.date.date(), r.blood_group, r.rh_type, r.blood_component,
         float(r.actual_demand), float(r.predicted_demand), float(r.prediction_error), "BACKTEST")
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO blood_actual_vs_predicted
           (avp_date, blood_group, rh_type, blood_component, actual_demand, predicted_demand, prediction_error, source)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "blood", "blood_demand_actual_vs_predicted.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[blood_actual_vs_predicted] inserted {len(rows)} rows")


def run():
    conn = get_import_connection()
    try:
        import_blood_demand(conn)
        import_blood_features(conn)
        import_blood_collection(conn)
        import_blood_inventory(conn)
        import_blood_batches(conn)
        import_blood_alerts(conn)
        import_blood_recommendations(conn)
        import_blood_model_comparison(conn)
        import_blood_avp(conn)
        print("Blood import complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
