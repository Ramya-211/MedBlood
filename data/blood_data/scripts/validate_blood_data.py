"""
validate_blood_data.py

Runs data-quality checks across all generated datasets and writes
BLOOD_DATA_QUALITY_REPORT.md with pass/fail results for each check.
"""

import pandas as pd
import numpy as np

BASE = "/home/claude/blood_data"

demand = pd.read_csv(f"{BASE}/synthetic/blood_patient_demand_SYNTHETIC.csv", parse_dates=["date"])
inventory = pd.read_csv(f"{BASE}/synthetic/blood_inventory_SYNTHETIC.csv", parse_dates=["date"])
batches = pd.read_csv(f"{BASE}/synthetic/blood_batches_SYNTHETIC.csv", parse_dates=["collection_date", "expiry_date"])
features = pd.read_csv(f"{BASE}/processed/blood_demand_features_SYNTHETIC.csv", parse_dates=["date"])

VALID_BG = {"A", "B", "AB", "O"}
VALID_RH = {"Positive", "Negative"}
VALID_COMP = {"Whole Blood", "RBC", "Platelets", "Plasma"}
VALID_EXPIRY_STATUS = {"Expired", "Near Expiry", "Safe"}

checks = []

def add_check(name, passed, detail=""):
    checks.append({"check": name, "passed": bool(passed), "detail": detail})

# 1. Duplicate IDs
add_check("No duplicate record_id in demand", demand["record_id"].is_unique)
add_check("No duplicate inventory_id in inventory", inventory["inventory_id"].is_unique)
add_check("No duplicate batch_id in batches", batches["batch_id"].is_unique)

# 2. Duplicate records (full-row duplicates on natural key)
dup_demand = demand.duplicated(subset=["date", "blood_group", "rh_type", "blood_component"]).sum()
add_check("No duplicate demand records (date+segment)", dup_demand == 0, f"{dup_demand} duplicates found")

dup_inv = inventory.duplicated(subset=["date", "blood_group", "rh_type", "blood_component"]).sum()
add_check("No duplicate inventory records (date+segment)", dup_inv == 0, f"{dup_inv} duplicates found")

# 3. Missing values
missing_demand = demand.isna().sum().sum()
add_check("No missing values in demand dataset", missing_demand == 0, f"{missing_demand} missing cells")

missing_inv = inventory.isna().sum().sum()
add_check("No missing values in inventory dataset", missing_inv == 0, f"{missing_inv} missing cells")

missing_batch = batches.isna().sum().sum()
add_check("No missing values in batches dataset", missing_batch == 0, f"{missing_batch} missing cells")

# 4. Invalid categories
add_check("All blood_group values valid (demand)", set(demand["blood_group"].unique()).issubset(VALID_BG))
add_check("All rh_type values valid (demand)", set(demand["rh_type"].unique()).issubset(VALID_RH))
add_check("All blood_component values valid (demand)", set(demand["blood_component"].unique()).issubset(VALID_COMP))
add_check("All expiry_status values valid (batches)", set(batches["expiry_status"].unique()).issubset(VALID_EXPIRY_STATUS))

# 5. Negative values
neg_cols_demand = ["units_requested", "units_issued", "units_transfused", "emergency_requests", "routine_requests"]
neg_demand = (demand[neg_cols_demand] < 0).any().any()
add_check("No negative values in demand dataset", not neg_demand)

neg_cols_inv = ["opening_stock", "units_received", "units_issued", "units_discarded", "units_expired", "closing_stock"]
neg_inv = (inventory[neg_cols_inv] < 0).any().any()
add_check("No negative values in inventory dataset", not neg_inv)

# 6. Invalid dates
add_check("No null dates in demand", demand["date"].notna().all())
add_check("No null dates in inventory", inventory["date"].notna().all())
bad_batch_dates = (batches["expiry_date"] < batches["collection_date"]).sum()
add_check("No expiry_date before collection_date", bad_batch_dates == 0, f"{bad_batch_dates} violations")

# 7. emergency + routine != requested
mismatch = (demand["emergency_requests"] + demand["routine_requests"] != demand["units_requested"]).sum()
add_check("emergency_requests + routine_requests == units_requested (all rows)", mismatch == 0, f"{mismatch} mismatches")

# 8. issued > requested
issued_gt_requested = (demand["units_issued"] > demand["units_requested"]).sum()
add_check("units_issued never exceeds units_requested", issued_gt_requested == 0, f"{issued_gt_requested} violations")

# 9. transfused > issued
transfused_gt_issued = (demand["units_transfused"] > demand["units_issued"]).sum()
add_check("units_transfused never exceeds units_issued", transfused_gt_issued == 0, f"{transfused_gt_issued} violations")

# 10. negative inventory
neg_closing = (inventory["closing_stock"] < 0).sum()
add_check("No negative closing_stock", neg_closing == 0, f"{neg_closing} violations")

# 11. incorrect inventory equation
calc_closing = (
    inventory["opening_stock"] + inventory["units_received"]
    - inventory["units_issued"] - inventory["units_discarded"] - inventory["units_expired"]
)
eq_violations = (calc_closing != inventory["closing_stock"]).sum()
add_check("Inventory equation holds for all rows", eq_violations == 0, f"{eq_violations} violations")

# 12. broken stock continuity
continuity_violations = 0
inv_sorted = inventory.sort_values(["blood_group", "rh_type", "blood_component", "date"])
for (bg, rh, comp), grp in inv_sorted.groupby(["blood_group", "rh_type", "blood_component"]):
    grp = grp.reset_index(drop=True)
    prev_closing = grp["closing_stock"].shift(1)
    mismatches = (grp["opening_stock"].iloc[1:].values != prev_closing.iloc[1:].values).sum()
    continuity_violations += mismatches
add_check("Stock continuity holds (next opening == prev closing)", continuity_violations == 0, f"{continuity_violations} violations")

# 13. expiry before collection (duplicate of #6 but kept for explicit traceability)
add_check("expiry_date strictly after collection_date", (batches["expiry_date"] > batches["collection_date"]).all())

# 14. invalid expiry status (derived correctly from dates)
REFERENCE_DATE = demand["date"].max()
NEAR_EXPIRY_WINDOW_DAYS = 5

def expected_status(row):
    if row["expiry_date"] < REFERENCE_DATE:
        return "Expired"
    elif (row["expiry_date"] - REFERENCE_DATE).days <= NEAR_EXPIRY_WINDOW_DAYS:
        return "Near Expiry"
    else:
        return "Safe"

batches["_expected_status"] = batches.apply(expected_status, axis=1)
status_mismatches = (batches["_expected_status"] != batches["expiry_status"]).sum()
add_check("expiry_status correctly derived from dates", status_mismatches == 0, f"{status_mismatches} mismatches")

# 15. ML data leakage check: lag/rolling features must not use same-day or future data
# Verify lag_1 equals prior day's daily_demand exactly, per segment
leakage_violations = 0
feat_sorted = features.sort_values(["blood_group", "rh_type", "blood_component", "date"])
for (bg, rh, comp), grp in feat_sorted.groupby(["blood_group", "rh_type", "blood_component"]):
    grp = grp.reset_index(drop=True)
    expected_lag1 = grp["daily_demand"].shift(1)
    diffs = (grp["lag_1"].iloc[1:].reset_index(drop=True) != expected_lag1.iloc[1:].reset_index(drop=True))
    leakage_violations += diffs.sum()
add_check("lag_1 feature correctly reflects prior day only (no leakage)", leakage_violations == 0, f"{leakage_violations} violations")

# ---------------------------------------------------------------------------
# Write report
# ---------------------------------------------------------------------------
n_pass = sum(c["passed"] for c in checks)
n_total = len(checks)

lines = []
lines.append("# BLOOD DATA QUALITY REPORT\n")
lines.append(f"**Checks passed: {n_pass} / {n_total}**\n")
lines.append("| Check | Result | Detail |")
lines.append("|---|---|---|")
for c in checks:
    result = "PASS" if c["passed"] else "**FAIL**"
    lines.append(f"| {c['check']} | {result} | {c['detail']} |")

report_text = "\n".join(lines)
with open(f"{BASE}/reports/BLOOD_DATA_QUALITY_REPORT.md", "w") as f:
    f.write(report_text)

print(f"Validation complete: {n_pass}/{n_total} checks passed.")
if n_pass < n_total:
    failed = [c["check"] for c in checks if not c["passed"]]
    print("FAILED CHECKS:", failed)
else:
    print("All checks passed.")
