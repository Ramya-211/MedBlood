"""
generate_medicine_demand.py

Generates the SYNTHETIC operational medicine demand dataset. This is
required because no real transaction/sales dataset with sufficient
medicine-wise demand detail was provided to this pipeline run.

Main demand variable: units_requested (documented as: quantity of the
medicine requested/needed at the pharmacy counter/ward on that date).

Output: medicine_data/synthetic/medicine_demand_SYNTHETIC.csv
"""

import numpy as np
import pandas as pd
from datetime import datetime

SEED = 55
rng = np.random.default_rng(SEED)

CATALOG_PATH = "/home/claude/medicine_data/synthetic/medicine_master_SYNTHETIC_placeholder.csv"
catalog = pd.read_csv(CATALOG_PATH)

START_DATE = datetime(2021, 1, 1)
END_DATE = datetime(2024, 12, 31)
DATES = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS = len(DATES)

# Category-level base demand multipliers (illustrative; higher for chronic-use
# categories like Antidiabetic/Antihypertensive, lower for episodic-use ones)
CATEGORY_BASE = {
    "Analgesic": 45, "Antibiotic": 30, "Antidiabetic": 40,
    "Antihypertensive": 42, "Antacid": 28, "Antihistamine": 22,
    "Vitamin/Supplement": 20, "Respiratory": 18, "Cardiac": 25,
    "Dermatological": 12,
}

# Category-level seasonal phase (days offset) -- e.g. respiratory/antihistamine
# medicines peak in different seasons than chronic-disease medicines
CATEGORY_SEASON_PHASE = {
    "Analgesic": 30, "Antibiotic": 200, "Antidiabetic": 0,
    "Antihypertensive": 10, "Antacid": 60, "Antihistamine": 250,
    "Vitamin/Supplement": 340, "Respiratory": 260, "Cardiac": 5,
    "Dermatological": 150,
}

records = []
record_id = 1

for _, med in catalog.iterrows():
    med_id, med_name, category = med["medicine_id"], med["medicine_name"], med["category"]
    base = CATEGORY_BASE.get(category, 20)
    # Medicine-specific scaling factor so medicines within a category still differ
    med_scale = rng.uniform(0.6, 1.4)
    seg_base = base * med_scale

    # Long-term trend (slow drift, some medicines growing, some declining)
    trend_direction = rng.choice([-1, 1], p=[0.35, 0.65])
    trend = np.linspace(0, trend_direction * seg_base * 0.3, N_DAYS)

    # Yearly seasonality with category-specific phase
    phase = CATEGORY_SEASON_PHASE.get(category, 0)
    day_of_year = np.array([d.timetuple().tm_yday for d in DATES])
    season = seg_base * 0.25 * np.sin(2 * np.pi * (day_of_year - phase) / 365.25)

    # Weekday effect (lower on Sundays for outpatient-driven demand)
    weekday = np.array([d.weekday() for d in DATES])
    weekday_effect = np.where(weekday == 6, -seg_base * 0.25, seg_base * 0.02)

    # Autocorrelated random walk + noise
    noise = rng.normal(0, seg_base * 0.10, N_DAYS)
    random_walk = np.cumsum(rng.normal(0, seg_base * 0.012, N_DAYS))
    random_walk -= random_walk.mean()

    # Occasional spikes (e.g. seasonal outbreaks) and drops (e.g. stockout weeks upstream)
    spike_days = rng.choice(N_DAYS, size=max(3, N_DAYS // 220), replace=False)
    spikes = np.zeros(N_DAYS)
    spikes[spike_days] = seg_base * rng.uniform(0.7, 1.8, size=len(spike_days))

    drop_days = rng.choice(N_DAYS, size=max(2, N_DAYS // 280), replace=False)
    drops = np.zeros(N_DAYS)
    drops[drop_days] = -seg_base * rng.uniform(0.3, 0.55, size=len(drop_days))

    raw_demand = seg_base + trend + season + weekday_effect + noise + random_walk + spikes + drops
    raw_demand = np.clip(raw_demand, 0, None)
    units_requested = np.round(raw_demand).astype(int)

    fulfillment_rate = np.clip(rng.normal(0.94, 0.05, N_DAYS), 0.5, 1.0)
    units_issued = np.minimum(np.round(units_requested * fulfillment_rate).astype(int), units_requested)

    dispense_rate = np.clip(rng.normal(0.97, 0.03, N_DAYS), 0.5, 1.0)
    units_dispensed = np.minimum(np.round(units_issued * dispense_rate).astype(int), units_issued)

    for i, d in enumerate(DATES):
        records.append({
            "record_id": record_id,
            "date": d.strftime("%Y-%m-%d"),
            "medicine_id": med_id,
            "medicine_name": med_name,
            "category": category,
            "units_requested": int(units_requested[i]),
            "units_issued": int(units_issued[i]),
            "units_dispensed": int(units_dispensed[i]),
        })
        record_id += 1

df = pd.DataFrame(records)

assert (df["units_issued"] <= df["units_requested"]).all()
assert (df["units_dispensed"] <= df["units_issued"]).all()
assert (df[["units_requested", "units_issued", "units_dispensed"]] >= 0).all().all()

df.sort_values(["date", "medicine_id"], inplace=True)
df.reset_index(drop=True, inplace=True)
df["record_id"] = range(1, len(df) + 1)

OUT_PATH = "/home/claude/medicine_data/synthetic/medicine_demand_SYNTHETIC.csv"
df.to_csv(OUT_PATH, index=False)

print(f"Generated {len(df):,} SYNTHETIC demand records -> {OUT_PATH}")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")
print(f"Medicines: {df['medicine_id'].nunique()}")
print(f"Random seed used: {SEED}")
