"""
run_import.py

Single entry point to (re)load the supplied datasets into MySQL.
Truncates the dataset tables first (users and import_log are preserved),
then runs the medicine and blood importers, so it is safe to re-run.
Original CSV files are only ever read, never modified.

Usage:
    python run_import.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

from app.importers.import_db import get_import_connection
from app.importers import medicine_importer, blood_importer

# Child tables first, parents last (FK order); FK checks are also disabled while truncating.
DATASET_TABLES = [
    "medicine_forecasts", "medicine_forecast_runs",  # model-generated from the dataset: regenerate after import
    "blood_forecasts", "blood_forecast_runs",
    "medicine_actual_vs_predicted", "medicine_model_comparison", "medicine_demand_anomalies",
    "medicine_seasonality", "medicine_trend_analysis", "medicine_volume_tiers",
    "medicine_recommendations", "medicine_alerts", "medicine_expiry_alerts", "medicine_batches",
    "medicine_inventory", "medicine_demand_features", "medicine_demand", "medicines",
    "blood_actual_vs_predicted", "blood_model_comparison", "blood_recommendations", "blood_alerts",
    "blood_batches", "blood_inventory", "blood_collection", "blood_demand_features", "blood_demand",
]


def reset_dataset_tables():
    conn = get_import_connection()
    try:
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in DATASET_TABLES:
            cur.execute(f"TRUNCATE TABLE `{t}`")  # table names come from the fixed list above
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print(f"Cleared {len(DATASET_TABLES)} dataset tables.")
    finally:
        conn.close()


if __name__ == "__main__":
    reset_dataset_tables()
    medicine_importer.run()
    blood_importer.run()
    print("All datasets imported.")
    print("NOTE: model-generated forecasts were cleared; run `python -m app.ml.medicine_ml train` to regenerate them.")
