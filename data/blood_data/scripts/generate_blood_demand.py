"""
generate_blood_demand.py

Generates the SYNTHETIC patient blood demand dataset.

IMPORTANT: This dataset is entirely SYNTHETIC. It does NOT represent real
patient records from any hospital, and must never be described as actual
Indian/Telangana hospital data.

Output: blood_data/synthetic/blood_patient_demand_SYNTHETIC.csv

Main PATIENT DEMAND variable: units_requested
(This is NOT the same as donation_volume / units_collected, which is SUPPLY.)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
START_DATE = datetime(2021, 1, 1)
END_DATE = datetime(2024, 12, 31)  # 4 years of daily data
DATES = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS = len(DATES)

BLOOD_GROUPS = ["A", "B", "AB", "O"]
RH_TYPES = ["Positive", "Negative"]
COMPONENTS = ["Whole Blood", "RBC", "Platelets", "Plasma"]

# Approximate real-world population prevalence weights (used only to make
# synthetic proportions look plausible -- NOT derived from any real dataset)
BG_WEIGHTS = {"A": 0.22, "B": 0.35, "AB": 0.07, "O": 0.36}
RH_WEIGHTS = {"Positive": 0.94, "Negative": 0.06}
COMPONENT_WEIGHTS = {"Whole Blood": 0.30, "RBC": 0.40, "Platelets": 0.15, "Plasma": 0.15}

# Baseline daily demand per (blood_group, rh_type, component) combination
BASE_DEMAND = 6.0

records = []
record_id = 1

for bg in BLOOD_GROUPS:
    for rh in RH_TYPES:
        for comp in COMPONENTS:
            # Segment-specific baseline scaled by rarity of the combination
            segment_weight = BG_WEIGHTS[bg] * RH_WEIGHTS[rh] * COMPONENT_WEIGHTS[comp]
            segment_base = max(1.0, BASE_DEMAND * segment_weight * 40)

            # Long-term linear trend (slow growth in demand over the years)
            trend = np.linspace(0, segment_base * 0.35, N_DAYS)

            # Yearly seasonality (e.g., higher demand in certain months -
            # illustrative synthetic seasonal wave, not derived from real data)
            day_of_year = np.array([d.timetuple().tm_yday for d in DATES])
            yearly_season = segment_base * 0.20 * np.sin(2 * np.pi * (day_of_year - 60) / 365.25)

            # Weekday/weekend effect: routine procedures lower on weekends
            weekday = np.array([d.weekday() for d in DATES])  # 0=Mon .. 6=Sun
            weekend_effect = np.where(weekday >= 5, -segment_base * 0.15, segment_base * 0.03)

            # Random walk component for realistic day-to-day autocorrelation
            noise = rng.normal(0, segment_base * 0.08, N_DAYS)
            random_walk = np.cumsum(rng.normal(0, segment_base * 0.01, N_DAYS))
            random_walk -= random_walk.mean()  # keep centered

            # Occasional demand spikes (e.g., mass casualty events, festival season)
            spike_days = rng.choice(N_DAYS, size=max(3, N_DAYS // 200), replace=False)
            spikes = np.zeros(N_DAYS)
            spikes[spike_days] = segment_base * rng.uniform(0.8, 2.0, size=len(spike_days))

            # Occasional low-demand periods (e.g., holidays, reduced elective surgery)
            low_periods = rng.choice(N_DAYS, size=max(2, N_DAYS // 300), replace=False)
            lows = np.zeros(N_DAYS)
            lows[low_periods] = -segment_base * rng.uniform(0.3, 0.6, size=len(low_periods))

            raw_demand = (
                segment_base
                + trend
                + yearly_season
                + weekend_effect
                + random_walk
                + noise
                + spikes
                + lows
            )
            raw_demand = np.clip(raw_demand, 0, None)
            units_requested = np.round(raw_demand).astype(int)

            # Split requested units into emergency vs routine (sum must equal requested)
            emergency_ratio = np.clip(rng.normal(0.30, 0.07, N_DAYS), 0.05, 0.75)
            emergency_requests = np.round(units_requested * emergency_ratio).astype(int)
            emergency_requests = np.minimum(emergency_requests, units_requested)
            routine_requests = units_requested - emergency_requests

            # Units issued <= units requested (occasional partial fulfillment)
            fulfillment_rate = np.clip(rng.normal(0.93, 0.05, N_DAYS), 0.5, 1.0)
            units_issued = np.round(units_requested * fulfillment_rate).astype(int)
            units_issued = np.minimum(units_issued, units_requested)

            # Units transfused <= units issued (some issued units not transfused: reserved/returned)
            transfusion_rate = np.clip(rng.normal(0.95, 0.04, N_DAYS), 0.5, 1.0)
            units_transfused = np.round(units_issued * transfusion_rate).astype(int)
            units_transfused = np.minimum(units_transfused, units_issued)

            for i, d in enumerate(DATES):
                records.append({
                    "record_id": record_id,
                    "date": d.strftime("%Y-%m-%d"),
                    "blood_group": bg,
                    "rh_type": rh,
                    "blood_component": comp,
                    "units_requested": int(units_requested[i]),
                    "units_issued": int(units_issued[i]),
                    "units_transfused": int(units_transfused[i]),
                    "emergency_requests": int(emergency_requests[i]),
                    "routine_requests": int(routine_requests[i]),
                })
                record_id += 1

df = pd.DataFrame(records)

# Sanity assertions (script-level self-check; full validation happens in validate_blood_data.py)
assert (df["emergency_requests"] + df["routine_requests"] == df["units_requested"]).all()
assert (df["units_issued"] <= df["units_requested"]).all()
assert (df["units_transfused"] <= df["units_issued"]).all()
assert (df[["units_requested", "units_issued", "units_transfused",
            "emergency_requests", "routine_requests"]] >= 0).all().all()

df.sort_values(["date", "blood_group", "rh_type", "blood_component"], inplace=True)
df.reset_index(drop=True, inplace=True)
df["record_id"] = range(1, len(df) + 1)

OUT_PATH = "/home/claude/blood_data/synthetic/blood_patient_demand_SYNTHETIC.csv"
df.to_csv(OUT_PATH, index=False)

print(f"Generated {len(df):,} SYNTHETIC patient demand records -> {OUT_PATH}")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")
print(f"Random seed used: {SEED}")
