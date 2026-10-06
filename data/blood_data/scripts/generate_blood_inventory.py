"""
generate_blood_inventory.py

Generates SYNTHETIC inventory and batch/expiry datasets, driven logically
from the SYNTHETIC patient demand dataset (units_issued) and the collection
placeholder (units_received). Enforces the inventory equation exactly and
guarantees stock continuity and non-negative closing stock.

Outputs:
  blood_data/synthetic/blood_inventory_SYNTHETIC.csv
  blood_data/synthetic/blood_batches_SYNTHETIC.csv
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

SEED = 123
rng = np.random.default_rng(SEED)

DEMAND_PATH = "/home/claude/blood_data/synthetic/blood_patient_demand_SYNTHETIC.csv"
demand = pd.read_csv(DEMAND_PATH, parse_dates=["date"])

# Shelf-life assumptions by component (days) - documented, not random
SHELF_LIFE_DAYS = {
    "Whole Blood": 35,
    "RBC": 42,
    "Platelets": 5,
    "Plasma": 365,
}

NEAR_EXPIRY_WINDOW_DAYS = 5  # documented threshold for "Near Expiry"
REFERENCE_DATE = demand["date"].max()  # last date in the dataset used as "today" reference

# Distinct short codes per component to avoid batch_id collisions
# (e.g. "Platelets" and "Plasma" both start with "PL" -- must be disambiguated)
COMPONENT_CODE = {
    "Whole Blood": "WB",
    "RBC": "RB",
    "Platelets": "PT",
    "Plasma": "PL",
}

segments = demand[["blood_group", "rh_type", "blood_component"]].drop_duplicates().reset_index(drop=True)

inventory_rows = []
batch_rows = []
inventory_id = 1
batch_id = 1

for _, seg in segments.iterrows():
    bg, rh, comp = seg["blood_group"], seg["rh_type"], seg["blood_component"]
    seg_demand = demand[
        (demand["blood_group"] == bg) & (demand["rh_type"] == rh) & (demand["blood_component"] == comp)
    ].sort_values("date").reset_index(drop=True)

    shelf_life = SHELF_LIFE_DAYS[comp]

    # Initial opening stock: rough buffer based on early average daily issuance
    initial_avg_issue = max(1, int(seg_demand["units_issued"].head(14).mean()))
    opening_stock = initial_avg_issue * 5

    # units_received: informed loosely by segment's issuance pattern plus
    # random supply variability, engineered so stock stays broadly viable.
    # This models incoming supply -- it is NOT derived from real donation data
    # (no real file was available for this run).
    base_receive = seg_demand["units_issued"].rolling(7, min_periods=1).mean().shift(1).fillna(initial_avg_issue)
    receive_noise = rng.normal(1.0, 0.25, len(seg_demand))
    units_received_series = np.clip(np.round(base_receive * receive_noise * 1.05), 0, None).astype(int)

    # Batches created when units are received (collection_date = date received)
    active_batches = []  # list of dicts: {batch_id, collection_date, expiry_date, units_remaining}

    for i, row in seg_demand.iterrows():
        date = row["date"]
        units_issued = int(row["units_issued"])
        units_received = int(units_received_series.iloc[i])

        # Create a new batch for units received this day (if any)
        if units_received > 0:
            expiry_date = date + timedelta(days=shelf_life)
            active_batches.append({
                "batch_id": batch_id,
                "collection_date": date,
                "expiry_date": expiry_date,
                "units_in_batch": units_received,
                "units_remaining": units_received,
            })
            batch_id += 1

        # Expire batches whose expiry_date <= current date (FIFO already partially consumed)
        units_expired_today = 0
        for b in active_batches:
            if b["expiry_date"] <= date and b["units_remaining"] > 0:
                units_expired_today += b["units_remaining"]
                b["units_remaining"] = 0
        active_batches = [b for b in active_batches if b["units_remaining"] > 0 or b["expiry_date"] > date]

        # Issue units FIFO (oldest batch first) against available remaining units
        remaining_to_issue = units_issued
        for b in sorted(active_batches, key=lambda x: x["collection_date"]):
            if remaining_to_issue <= 0:
                break
            take = min(b["units_remaining"], remaining_to_issue)
            b["units_remaining"] -= take
            remaining_to_issue -= take
        actual_units_issued = units_issued - remaining_to_issue  # capped by available stock

        # Discards: small stochastic wastage (e.g., damaged units), documented rate
        available_after_issue = sum(b["units_remaining"] for b in active_batches)
        discard_rate = 0.01  # documented 1% wastage assumption
        units_discarded = int(rng.binomial(max(0, available_after_issue), discard_rate)) if available_after_issue > 0 else 0
        # Remove discarded units from oldest batches
        remaining_to_discard = units_discarded
        for b in sorted(active_batches, key=lambda x: x["collection_date"]):
            if remaining_to_discard <= 0:
                break
            take = min(b["units_remaining"], remaining_to_discard)
            b["units_remaining"] -= take
            remaining_to_discard -= take
        units_discarded -= remaining_to_discard  # actual discarded, capped

        active_batches = [b for b in active_batches if b["units_remaining"] > 0]

        closing_stock = opening_stock + units_received - actual_units_issued - units_discarded - units_expired_today
        closing_stock = max(0, closing_stock)  # never negative, guaranteed by construction

        inventory_rows.append({
            "inventory_id": inventory_id,
            "date": date.strftime("%Y-%m-%d"),
            "blood_group": bg,
            "rh_type": rh,
            "blood_component": comp,
            "opening_stock": int(opening_stock),
            "units_received": int(units_received),
            "units_issued": int(actual_units_issued),
            "units_discarded": int(units_discarded),
            "units_expired": int(units_expired_today),
            "closing_stock": int(closing_stock),
        })
        inventory_id += 1

        opening_stock = closing_stock  # continuity: next day's opening = today's closing

    # Record final batch states (as of REFERENCE_DATE) for the batch/expiry dataset
    # We regenerate full batch history by re-simulating (kept simple: re-run collection loop for batches)

for _, seg in segments.iterrows():
    bg, rh, comp = seg["blood_group"], seg["rh_type"], seg["blood_component"]
    seg_demand = demand[
        (demand["blood_group"] == bg) & (demand["rh_type"] == rh) & (demand["blood_component"] == comp)
    ].sort_values("date").reset_index(drop=True)
    shelf_life = SHELF_LIFE_DAYS[comp]

    initial_avg_issue = max(1, int(seg_demand["units_issued"].head(14).mean()))
    base_receive = seg_demand["units_issued"].rolling(7, min_periods=1).mean().shift(1).fillna(initial_avg_issue)
    rng2 = np.random.default_rng(hash((bg, rh, comp)) % (2**32))
    receive_noise = rng2.normal(1.0, 0.25, len(seg_demand))
    units_received_series = np.clip(np.round(base_receive * receive_noise * 1.05), 0, None).astype(int)

    active_batches = []
    for i, row in seg_demand.iterrows():
        date = row["date"]
        units_issued = int(row["units_issued"])
        units_received = int(units_received_series.iloc[i])

        if units_received > 0:
            expiry_date = date + timedelta(days=shelf_life)
            active_batches.append({
                "batch_id": f"BT{bg}{rh[0]}{COMPONENT_CODE[comp]}{date.strftime('%Y%m%d')}",
                "collection_date": date,
                "expiry_date": expiry_date,
                "units_in_batch": units_received,
                "units_remaining": units_received,
            })

        for b in active_batches:
            if b["expiry_date"] <= date and b["units_remaining"] > 0:
                b["units_remaining"] = 0

        remaining_to_issue = units_issued
        for b in sorted(active_batches, key=lambda x: x["collection_date"]):
            if remaining_to_issue <= 0:
                break
            take = min(b["units_remaining"], remaining_to_issue)
            b["units_remaining"] -= take
            remaining_to_issue -= take

        active_batches = [b for b in active_batches if b["units_remaining"] > 0]

    # After simulating to end of series, record remaining batches as the batch table
    for b in active_batches:
        if b["expiry_date"] < REFERENCE_DATE:
            status = "Expired"
        elif (b["expiry_date"] - REFERENCE_DATE).days <= NEAR_EXPIRY_WINDOW_DAYS:
            status = "Near Expiry"
        else:
            status = "Safe"

        batch_rows.append({
            "batch_id": b["batch_id"],
            "collection_date": b["collection_date"].strftime("%Y-%m-%d"),
            "expiry_date": b["expiry_date"].strftime("%Y-%m-%d"),
            "blood_group": bg,
            "rh_type": rh,
            "blood_component": comp,
            "units_in_batch": int(b["units_in_batch"]),
            "units_remaining": int(b["units_remaining"]),
            "expiry_status": status,
        })

inv_df = pd.DataFrame(inventory_rows)
batch_df = pd.DataFrame(batch_rows)

# Verify inventory equation holds exactly
check = (
    inv_df["opening_stock"] + inv_df["units_received"]
    - inv_df["units_issued"] - inv_df["units_discarded"] - inv_df["units_expired"]
)
assert (check == inv_df["closing_stock"]).all(), "Inventory equation violated!"
assert (inv_df["closing_stock"] >= 0).all(), "Negative closing stock found!"

# Verify continuity: next day's opening == previous day's closing, per segment
inv_df_sorted = inv_df.sort_values(["blood_group", "rh_type", "blood_component", "date"])
for (bg, rh, comp), grp in inv_df_sorted.groupby(["blood_group", "rh_type", "blood_component"]):
    grp = grp.reset_index(drop=True)
    prev_closing = grp["closing_stock"].shift(1)
    match = (grp["opening_stock"].iloc[1:].values == prev_closing.iloc[1:].values)
    assert match.all(), f"Stock continuity broken for {bg} {rh} {comp}"

INV_OUT = "/home/claude/blood_data/synthetic/blood_inventory_SYNTHETIC.csv"
BATCH_OUT = "/home/claude/blood_data/synthetic/blood_batches_SYNTHETIC.csv"
inv_df.to_csv(INV_OUT, index=False)
batch_df.to_csv(BATCH_OUT, index=False)

print(f"Generated {len(inv_df):,} inventory records -> {INV_OUT}")
print(f"Generated {len(batch_df):,} batch records -> {BATCH_OUT}")
print("Inventory equation and stock continuity verified.")
print(f"Reference date for expiry status: {REFERENCE_DATE.strftime('%Y-%m-%d')}")
