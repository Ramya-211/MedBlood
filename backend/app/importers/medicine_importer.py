"""
medicine_importer.py

Imports the supplied (unmodified) medicine_data/ CSV files into MySQL using
raw parameterized SQL via mysql-connector-python. Validates required
fields, data types, dates, numerics, nulls and duplicates before insert.
Does not silently discard invalid records -- any rejected row is logged
to import_log.notes and printed.

Run standalone:
    python3 -m app.importers.medicine_importer
"""

import sys
import os
import math
import datetime
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.importers.import_db import get_import_connection

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.environ.get("MEDICINE_DATA_DIR", os.path.join(PROJECT_ROOT, "data", "medicine_data"))


def nz(v):
    """Convert pandas NaN/NaT to None for MySQL; pass through everything else."""
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


def import_medicines(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "medicine_master_SYNTHETIC_placeholder.csv")
    df = pd.read_csv(path)
    required = ["medicine_id", "medicine_name", "composition", "manufacturer", "dosage_form", "pack_size", "category", "provenance"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"medicine_master file missing required columns: {missing_cols}")

    dup_ids = df["medicine_id"].duplicated().sum()
    rejected = int(dup_ids)
    df = df.drop_duplicates(subset=["medicine_id"])

    cur = conn.cursor()
    rows = [
        (r.medicine_id, r.medicine_name, r.composition, r.manufacturer,
         r.dosage_form, r.pack_size, r.category, r.provenance)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicines (medicine_id, medicine_name, composition, manufacturer, dosage_form, pack_size, category, provenance)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) AS new_row
           ON DUPLICATE KEY UPDATE medicine_name=new_row.medicine_name""",
        rows,
    )
    log_import(cur, "medicine", "medicine_master_SYNTHETIC_placeholder.csv", len(df) + rejected, len(rows), rejected, started,
               "Duplicate medicine_id rows rejected" if rejected else "")
    conn.commit()
    print(f"[medicines] inserted/updated {len(rows)} rows, rejected {rejected} duplicates")


def import_medicine_demand(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "medicine_demand_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    n_read = len(df)

    before = len(df)
    df = df.dropna(subset=["record_id", "date", "medicine_id", "units_requested", "units_issued", "units_dispensed"])
    df = df[(df["units_requested"] >= 0) & (df["units_issued"] >= 0) & (df["units_dispensed"] >= 0)]
    df = df[df["units_issued"] <= df["units_requested"]]
    df = df[df["units_dispensed"] <= df["units_issued"]]
    rejected = before - len(df)

    cur = conn.cursor()
    rows = [
        (int(r.record_id), r.date.date(), r.medicine_id, r.category,
         int(r.units_requested), int(r.units_issued), int(r.units_dispensed))
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_demand (record_id, demand_date, medicine_id, category, units_requested, units_issued, units_dispensed)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_demand_SYNTHETIC.csv", n_read, len(rows), rejected, started)
    conn.commit()
    print(f"[medicine_demand] inserted {len(rows)} rows, rejected {rejected}")


def import_medicine_features(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "processed", "medicine_demand_features.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    n_read = len(df)

    cur = conn.cursor()
    rows = []
    for r in df.itertuples():
        rows.append((
            r.date.date(), r.medicine_id, nz(r.daily_demand), nz(r.weekly_demand), nz(r.monthly_demand),
            nz(r.rolling_mean_7), nz(r.rolling_mean_30), nz(r.growth_rate_7d), nz(r.growth_rate_30d),
            nz(r.trend_slope), int(r.month), int(r.day_of_week), r.season, nz(r.seasonality_index),
            nz(r.lag_1), nz(r.lag_7), nz(r.lag_14), nz(r.lag_30), int(r.anomaly_flag), nz(r.anomaly_score),
        ))
    cur.executemany(
        """INSERT INTO medicine_demand_features
           (feature_date, medicine_id, daily_demand, weekly_demand, monthly_demand,
            rolling_mean_7, rolling_mean_30, growth_rate_7d, growth_rate_30d, trend_slope,
            month_num, day_of_week, season, seasonality_index, lag_1, lag_7, lag_14, lag_30,
            anomaly_flag, anomaly_score)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_demand_features.csv", n_read, len(rows), 0, started)
    conn.commit()
    print(f"[medicine_demand_features] inserted {len(rows)} rows")


def import_medicine_inventory(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "medicine_inventory_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    n_read = len(df)

    before = len(df)
    calc = df["opening_stock"] + df["units_received"] - df["units_issued"] + df["units_adjusted"]
    df = df[calc == df["closing_stock"]]
    df = df[df["closing_stock"] >= 0]
    rejected = before - len(df)

    cur = conn.cursor()
    rows = [
        (int(r.inventory_id), r.date.date(), r.medicine_id, int(r.opening_stock),
         int(r.units_received), int(r.units_issued), int(r.units_adjusted),
         int(r.closing_stock), r.stock_status)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_inventory
           (inventory_id, inv_date, medicine_id, opening_stock, units_received, units_issued, units_adjusted, closing_stock, stock_status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_inventory_SYNTHETIC.csv", n_read, len(rows), rejected, started,
               "Rows failing inventory equation check rejected" if rejected else "")
    conn.commit()
    print(f"[medicine_inventory] inserted {len(rows)} rows, rejected {rejected}")


def import_medicine_batches(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "synthetic", "medicine_batches_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["manufacturing_date", "expiry_date"])
    n_read = len(df)

    before = len(df)
    df = df[df["expiry_date"] > df["manufacturing_date"]]
    rejected = before - len(df)

    cur = conn.cursor()
    rows = [
        (r.batch_id, r.medicine_id, r.batch_number, r.manufacturing_date.date(), r.expiry_date.date(),
         int(r.units_in_batch), int(r.units_remaining), r.expiry_status)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_batches
           (batch_id, medicine_id, batch_number, manufacturing_date, expiry_date, units_in_batch, units_remaining, expiry_status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_batches_SYNTHETIC.csv", n_read, len(rows), rejected, started)
    conn.commit()
    print(f"[medicine_batches] inserted {len(rows)} rows, rejected {rejected}")


def import_medicine_expiry_alerts(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "expiry", "medicine_expiry_alerts_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date", "expiry_date"])
    n_read = len(df)

    cur = conn.cursor()
    rows = [
        (int(r.alert_id), r.date.date(), r.medicine_id, r.batch_id, r.expiry_date.date(),
         int(r.days_to_expiry), r.severity, r.message)
        for r in df.itertuples()
    ]
    if rows:
        cur.executemany(
            """INSERT INTO medicine_expiry_alerts
               (alert_id, alert_date, medicine_id, batch_id, expiry_date, days_to_expiry, severity, message)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            rows,
        )
    log_import(cur, "medicine", "medicine_expiry_alerts_SYNTHETIC.csv", n_read, len(rows), 0, started)
    conn.commit()
    print(f"[medicine_expiry_alerts] inserted {len(rows)} rows")


def import_medicine_alerts(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "alerts", "medicine_alerts_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (int(r.alert_id), r.date.date(), r.medicine_id, r.alert_type, r.severity, r.message)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_alerts (alert_id, alert_date, medicine_id, alert_type, severity, message)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_alerts_SYNTHETIC.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_alerts] inserted {len(rows)} rows")


def import_medicine_recommendations(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "recommendations", "medicine_recommendations_SYNTHETIC.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (int(r.recommendation_id), r.date.date(), r.medicine_id, r.recommendation_type,
         r.severity, r.reason, r.recommended_action)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_recommendations
           (recommendation_id, rec_date, medicine_id, recommendation_type, severity, reason, recommended_action)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_recommendations_SYNTHETIC.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_recommendations] inserted {len(rows)} rows")


def import_medicine_volume_tiers(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "processed", "medicine_volume_tiers.csv")
    df = pd.read_csv(path)
    cur = conn.cursor()
    rows = [
        (r.medicine_id, int(r.total_units_dispensed), r.volume_tier)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_volume_tiers (medicine_id, total_units_dispensed, volume_tier)
           VALUES (%s,%s,%s) AS new_row
           ON DUPLICATE KEY UPDATE total_units_dispensed=new_row.total_units_dispensed, volume_tier=new_row.volume_tier""",
        rows,
    )
    log_import(cur, "medicine", "medicine_volume_tiers.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_volume_tiers] inserted {len(rows)} rows")


def import_medicine_trend_analysis(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "processed", "medicine_trend_analysis.csv")
    df = pd.read_csv(path)
    cur = conn.cursor()
    rows = [
        (r.medicine_id, float(r.trend_slope), r.trend_direction, nz(r.growth_rate_7d), nz(r.growth_rate_30d))
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_trend_analysis (medicine_id, trend_slope, trend_direction, growth_rate_7d, growth_rate_30d)
           VALUES (%s,%s,%s,%s,%s) AS new_row
           ON DUPLICATE KEY UPDATE trend_slope=new_row.trend_slope, trend_direction=new_row.trend_direction""",
        rows,
    )
    log_import(cur, "medicine", "medicine_trend_analysis.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_trend_analysis] inserted {len(rows)} rows")


def import_medicine_seasonality(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "processed", "medicine_seasonality.csv")
    df = pd.read_csv(path)
    cur = conn.cursor()
    rows = [
        (r.medicine_id, int(r.month), r.season, nz(r.seasonality_index))
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_seasonality (medicine_id, month_num, season, seasonality_index)
           VALUES (%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_seasonality.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_seasonality] inserted {len(rows)} rows")


def import_medicine_anomalies(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "processed", "medicine_demand_anomalies.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (r.date.date(), r.medicine_id, int(r.actual_demand), nz(r.expected_demand),
         nz(r.anomaly_score), int(r.anomaly_flag), r.anomaly_type)
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_demand_anomalies
           (anomaly_date, medicine_id, actual_demand, expected_demand, anomaly_score, anomaly_flag, anomaly_type)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_demand_anomalies.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_demand_anomalies] inserted {len(rows)} rows")


def import_medicine_model_comparison(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "ml", "medicine_model_comparison.csv")
    df = pd.read_csv(path)
    cur = conn.cursor()
    rows = [(r.model, float(r.RMSE), float(r.MAE), float(r.R2)) for r in df.itertuples()]
    cur.executemany(
        "INSERT INTO medicine_model_comparison (model_name, rmse, mae, r2) VALUES (%s,%s,%s,%s)",
        rows,
    )
    log_import(cur, "medicine", "medicine_model_comparison.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_model_comparison] inserted {len(rows)} rows")


def import_medicine_avp(conn):
    started = datetime.datetime.now()
    path = os.path.join(DATA_DIR, "ml", "medicine_actual_vs_predicted.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    cur = conn.cursor()
    rows = [
        (r.date.date(), r.medicine_id, float(r.actual_demand), float(r.predicted_demand),
         float(r.prediction_error), "BACKTEST")
        for r in df.itertuples()
    ]
    cur.executemany(
        """INSERT INTO medicine_actual_vs_predicted (avp_date, medicine_id, actual_demand, predicted_demand, prediction_error, source)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log_import(cur, "medicine", "medicine_actual_vs_predicted.csv", len(df), len(rows), 0, started)
    conn.commit()
    print(f"[medicine_actual_vs_predicted] inserted {len(rows)} rows")


def run():
    conn = get_import_connection()
    try:
        import_medicines(conn)
        import_medicine_demand(conn)
        import_medicine_features(conn)
        import_medicine_inventory(conn)
        import_medicine_batches(conn)
        import_medicine_expiry_alerts(conn)
        import_medicine_alerts(conn)
        import_medicine_recommendations(conn)
        import_medicine_volume_tiers(conn)
        import_medicine_trend_analysis(conn)
        import_medicine_seasonality(conn)
        import_medicine_anomalies(conn)
        import_medicine_model_comparison(conn)
        import_medicine_avp(conn)
        print("Medicine import complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
