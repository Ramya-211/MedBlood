"""
generate_blood_collection_placeholder.py

NOTE ON PROVENANCE:
--------------------
The project brief describes a REAL blood donation/collection dataset with
columns similar to: date, blood_type, donation_volume, data_type.

That real file was NOT provided to this pipeline run. To avoid fabricating
real-world data (which is explicitly forbidden), this script does NOT create
a file named *_REAL.csv. Instead it creates a clearly labeled SYNTHETIC
placeholder with the same schema, so the rest of the pipeline (inventory,
supply-side analysis) can run end-to-end and be validated structurally.

ACTION REQUIRED FROM PROJECT OWNER:
When the actual real donation dataset is available, drop it at:
    blood_data/real/blood_collection_REAL.csv
with columns: date, blood_type, donation_volume, data_type
and re-run generate_blood_inventory.py. Do not delete this note.

Output: blood_data/synthetic/blood_collection_SYNTHETIC_placeholder.csv
"""

import numpy as np
import pandas as pd
from datetime import datetime

SEED = 7
rng = np.random.default_rng(SEED)

START_DATE = datetime(2021, 1, 1)
END_DATE = datetime(2024, 12, 31)
DATES = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS = len(DATES)

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
TYPE_WEIGHTS = {
    "A+": 0.20, "A-": 0.02, "B+": 0.32, "B-": 0.03,
    "AB+": 0.06, "AB-": 0.01, "O+": 0.33, "O-": 0.03,
}

records = []
for bt in BLOOD_TYPES:
    base = 30 * TYPE_WEIGHTS[bt] * 10
    trend = np.linspace(0, base * 0.2, N_DAYS)
    day_of_year = np.array([d.timetuple().tm_yday for d in DATES])
    season = base * 0.15 * np.sin(2 * np.pi * (day_of_year - 100) / 365.25)
    noise = rng.normal(0, base * 0.12, N_DAYS)
    volume = np.clip(base + trend + season + noise, 0, None)
    volume = np.round(volume).astype(int)

    for i, d in enumerate(DATES):
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "blood_type": bt,
            "donation_volume": int(volume[i]),
            "data_type": "SYNTHETIC_PLACEHOLDER",
        })

df = pd.DataFrame(records)
df.sort_values(["date", "blood_type"], inplace=True)
df.reset_index(drop=True, inplace=True)

OUT_PATH = "/home/claude/blood_data/synthetic/blood_collection_SYNTHETIC_placeholder.csv"
df.to_csv(OUT_PATH, index=False)
print(f"Generated {len(df):,} SYNTHETIC PLACEHOLDER collection records -> {OUT_PATH}")
print("Reminder: replace with real data at blood_data/real/blood_collection_REAL.csv when available.")
