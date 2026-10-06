"""
generate_medicine_inventory.py

Generates the SYNTHETIC medicine inventory dataset, driven logically from
medicine demand (units_issued). Enforces the inventory equation exactly and
guarantees stock continuity and non-negative closing stock.

Inventory equation:
    closing_stock = opening_stock + units_received - units_issued + units_adjusted

Output: medicine_data/synthetic/medicine_inventory_SYNTHETIC.csv
        (also copied to medicine_data/inventory/ per required file structure)
"""

import numpy as np
import pandas as pd

SEED = 321
rng = np.random.default_rng(SEED)

DEMAND_PATH = "/home/claude/medicine_data/synthetic/medicine_demand_SYNTHETIC.csv"
demand = pd.read_csv(DEMAND_PATH, parse_dates=["date"])

# Documented stock-status thresholds (days-of-cover based on trailing 30-day
# average daily issuance), same approach as the blood module for consistency.
CRITICAL_DAYS = 3
LOW_DAYS = 7
OVERSTOCK_DAYS = 45

inventory_rows = []
inventory_id = 1

medicines = demand[["medicine_id", "medicine_name"]].drop_duplicates().reset_index(drop=True)

for _, med in medicines.iterrows():
    med_id, med_name = med["medicine_id"], med["medicine_name"]
    seg = demand[demand["medicine_id"] == med_id].sort_values("date").reset_index(drop=True)

    initial_avg_issue = max(1, int(seg["units_issued"].head(14).mean()))
    opening_stock = initial_avg_issue * 7  # initial buffer

    # units_received modeled from a rolling average of recent issuance plus noise,
    # engineered as a restocking proxy since no real procurement/receipt data exists.
    base_receive = seg["units_issued"].rolling(7, min_periods=1).mean().shift(1).fillna(initial_avg_issue)
    receive_noise = rng.normal(1.0, 0.22, len(seg))
    # Restock less frequently (every ~5 days) in a lumpier, more realistic pattern
    restock_day = (np.arange(len(seg)) % 5 == 0)
    units_received_series = np.where(
        restock_day,
        np.clip(np.round(base_receive * 5 * receive_noise), 0, None),
        0,
    ).astype(int)

    for i, row in seg.iterrows():
        units_issued_req = int(row["units_issued"])
        units_received = int(units_received_series[i])

        # Cap issuance by available stock (opening + received) so inventory never goes negative
        available = opening_stock + units_received
        actual_issued = min(units_issued_req, available)

        # Rare small stock adjustments (e.g. audit corrections, damages) - documented ~0.5% of opening stock
        adjustment_prob = 0.03
        if rng.random() < adjustment_prob:
            units_adjusted = int(rng.integers(-max(1, int(opening_stock * 0.01)), max(2, int(opening_stock * 0.01)) + 1))
        else:
            units_adjusted = 0
        # Prevent adjustment from pushing stock negative
        projected = opening_stock + units_received - actual_issued + units_adjusted
        if projected < 0:
            units_adjusted = -(opening_stock + units_received - actual_issued)
            projected = 0

        closing_stock = max(0, projected)

        # Stock status from documented days-of-cover thresholds
        recent_window = seg["units_issued"].iloc[max(0, i - 29): i + 1]
        avg_daily_issue = recent_window.mean() if len(recent_window) > 0 else 0
        days_of_cover = closing_stock / avg_daily_issue if avg_daily_issue > 0 else (999 if closing_stock > 0 else 0)

        if days_of_cover < CRITICAL_DAYS:
            stock_status = "Critical"
        elif days_of_cover < LOW_DAYS:
            stock_status = "Low"
        elif days_of_cover > OVERSTOCK_DAYS:
            stock_status = "Overstock"
        else:
            stock_status = "Normal"

        inventory_rows.append({
            "inventory_id": inventory_id,
            "date": row["date"].strftime("%Y-%m-%d"),
            "medicine_id": med_id,
            "medicine_name": med_name,
            "opening_stock": int(opening_stock),
            "units_received": int(units_received),
            "units_issued": int(actual_issued),
            "units_adjusted": int(units_adjusted),
            "closing_stock": int(closing_stock),
            "stock_status": stock_status,
        })
        inventory_id += 1

        opening_stock = closing_stock  # continuity

inv_df = pd.DataFrame(inventory_rows)

# Verify inventory equation
calc = inv_df["opening_stock"] + inv_df["units_received"] - inv_df["units_issued"] + inv_df["units_adjusted"]
assert (calc == inv_df["closing_stock"]).all(), "Inventory equation violated!"
assert (inv_df["closing_stock"] >= 0).all(), "Negative closing stock found!"

# Verify continuity per medicine
inv_sorted = inv_df.sort_values(["medicine_id", "date"])
for med_id, grp in inv_sorted.groupby("medicine_id"):
    grp = grp.reset_index(drop=True)
    prev_closing = grp["closing_stock"].shift(1)
    match = (grp["opening_stock"].iloc[1:].values == prev_closing.iloc[1:].values)
    assert match.all(), f"Stock continuity broken for {med_id}"

OUT_PATH_SYN = "/home/claude/medicine_data/synthetic/medicine_inventory_SYNTHETIC.csv"
OUT_PATH_INV = "/home/claude/medicine_data/inventory/medicine_inventory_SYNTHETIC.csv"
inv_df.to_csv(OUT_PATH_SYN, index=False)
inv_df.to_csv(OUT_PATH_INV, index=False)

print(f"Generated {len(inv_df):,} inventory records -> {OUT_PATH_SYN}")
print("Inventory equation and stock continuity verified.")
print(f"Stock status distribution:\n{inv_df['stock_status'].value_counts()}")
