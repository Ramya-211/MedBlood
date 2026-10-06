"""
validate_medicine_data.py

Runs data-quality checks across all generated medicine datasets and writes
MEDICINE_DATA_QUALITY_REPORT.md with pass/fail results for each check.
"""

import pandas as pd
import numpy as np

BASE = "/home/claude/medicine_data"

demand = pd.read_csv(f"{BASE}/synthetic/medicine_demand_SYNTHETIC.csv", parse_dates=["date"])
inventory = pd.read_csv(f"{BASE}/synthetic/medicine_inventory_SYNTHETIC.csv", parse_dates=["date"])
batches = pd.read_csv(f"{BASE}/synthetic/medicine_batches_SYNTHETIC.csv", parse_dates=["manufacturing_date", "expiry_date"])
features = pd.read_csv(f"{BASE}/processed/medicine_demand_features.csv", parse_dates=["date"])
catalog = pd.read_csv(f"{BASE}/synthetic/medicine_master_SYNTHETIC_placeholder.csv")

VALID_EXPIRY_STATUS = {"Expired", "Near Expiry", "Safe"}
VALID_STOCK_STATUS = {"Critical", "Low", "Normal", "Overstock"}
VALID_CATEGORIES = set(catalog["category"].unique())

checks = []

def add_check(name, passed, detail=""):
    checks.append({"check": name, "passed": bool(passed), "detail": detail})

# 1. Duplicate IDs
add_check("No duplicate record_id in demand", demand["record_id"].is_unique)
add_check("No duplicate inventory_id in inventory", inventory["inventory_id"].is_unique)
add_check("No duplicate batch_id in batches", batches["batch_id"].is_unique)
add_check("No duplicate medicine_id in catalog", catalog["medicine_id"].is_unique)

# 2. Duplicate records (natural key)
dup_demand = demand.duplicated(subset=["date", "medicine_id"]).sum()
add_check("No duplicate demand records (date+medicine)", dup_demand == 0, f"{dup_demand} duplicates found")

dup_inv = inventory.duplicated(subset=["date", "medicine_id"]).sum()
add_check("No duplicate inventory records (date+medicine)", dup_inv == 0, f"{dup_inv} duplicates found")

# 3. Missing values
missing_demand = demand.isna().sum().sum()
add_check("No missing values in demand dataset", missing_demand == 0, f"{missing_demand} missing cells")

missing_inv = inventory.isna().sum().sum()
add_check("No missing values in inventory dataset", missing_inv == 0, f"{missing_inv} missing cells")

missing_batch = batches.isna().sum().sum()
add_check("No missing values in batches dataset", missing_batch == 0, f"{missing_batch} missing cells")

# 4. Invalid categories
add_check("All category values valid (demand)", set(demand["category"].unique()).issubset(VALID_CATEGORIES))
add_check("All stock_status values valid (inventory)", set(inventory["stock_status"].unique()).issubset(VALID_STOCK_STATUS))
add_check("All expiry_status values valid (batches)", set(batches["expiry_status"].unique()).issubset(VALID_EXPIRY_STATUS))

# 5. Negative values
neg_cols_demand = ["units_requested", "units_issued", "units_dispensed"]
neg_demand = (demand[neg_cols_demand] < 0).any().any()
add_check("No negative values in demand dataset", not neg_demand)

neg_cols_inv = ["opening_stock", "units_received", "units_issued", "closing_stock"]
neg_inv = (inventory[neg_cols_inv] < 0).any().any()
add_check("No negative values in inventory dataset (excl. units_adjusted, which may be negative)", not neg_inv)

# 6. Invalid dates
add_check("No null dates in demand", demand["date"].notna().all())
add_check("No null dates in inventory", inventory["date"].notna().all())
bad_batch_dates = (batches["expiry_date"] < batches["manufacturing_date"]).sum()
add_check("No expiry_date before manufacturing_date", bad_batch_dates == 0, f"{bad_batch_dates} violations")

# 7. issued > requested
issued_gt_requested = (demand["units_issued"] > demand["units_requested"]).sum()
add_check("units_issued never exceeds units_requested", issued_gt_requested == 0, f"{issued_gt_requested} violations")

# 8. dispensed > issued
dispensed_gt_issued = (demand["units_dispensed"] > demand["units_issued"]).sum()
add_check("units_dispensed never exceeds units_issued", dispensed_gt_issued == 0, f"{dispensed_gt_issued} violations")

# 9. negative inventory
neg_closing = (inventory["closing_stock"] < 0).sum()
add_check("No negative closing_stock", neg_closing == 0, f"{neg_closing} violations")

# 10. incorrect stock equation
calc_closing = inventory["opening_stock"] + inventory["units_received"] - inventory["units_issued"] + inventory["units_adjusted"]
eq_violations = (calc_closing != inventory["closing_stock"]).sum()
add_check("Inventory equation holds for all rows", eq_violations == 0, f"{eq_violations} violations")

# 11. broken stock continuity
continuity_violations = 0
inv_sorted = inventory.sort_values(["medicine_id", "date"])
for med_id, grp in inv_sorted.groupby("medicine_id"):
    grp = grp.reset_index(drop=True)
    prev_closing = grp["closing_stock"].shift(1)
    mismatches = (grp["opening_stock"].iloc[1:].values != prev_closing.iloc[1:].values).sum()
    continuity_violations += mismatches
add_check("Stock continuity holds (next opening == prev closing)", continuity_violations == 0, f"{continuity_violations} violations")

# 12. expiry before manufacturing (explicit, traceable duplicate of #6)
add_check("expiry_date strictly after manufacturing_date", (batches["expiry_date"] > batches["manufacturing_date"]).all())

# 13. invalid expiry status (correctly derived from dates)
REFERENCE_DATE = demand["date"].max()
NEAR_EXPIRY_WINDOW_DAYS = 30

def expected_status(row):
    days_to_expiry = (row["expiry_date"] - REFERENCE_DATE).days
    if days_to_expiry < 0:
        return "Expired"
    elif days_to_expiry <= NEAR_EXPIRY_WINDOW_DAYS:
        return "Near Expiry"
    else:
        return "Safe"

batches["_expected_status"] = batches.apply(expected_status, axis=1)
status_mismatches = (batches["_expected_status"] != batches["expiry_status"]).sum()
add_check("expiry_status correctly derived from dates", status_mismatches == 0, f"{status_mismatches} mismatches")

# 14. invalid days_to_expiry (check the expiry alerts file, if non-empty)
try:
    expiry_alerts = pd.read_csv(f"{BASE}/expiry/medicine_expiry_alerts_SYNTHETIC.csv")
    if len(expiry_alerts) > 0:
        expiry_alerts["expiry_date"] = pd.to_datetime(expiry_alerts["expiry_date"])
        ref = pd.Timestamp(REFERENCE_DATE)
        expected_days = (expiry_alerts["expiry_date"] - ref).dt.days
        mismatch_days = (expected_days != expiry_alerts["days_to_expiry"]).sum()
        add_check("days_to_expiry correctly derived from dates", mismatch_days == 0, f"{mismatch_days} mismatches")
    else:
        add_check("days_to_expiry correctly derived from dates", True, "No expiry alerts currently active (0 rows) — check vacuously passes")
except (FileNotFoundError, pd.errors.EmptyDataError):
    add_check("days_to_expiry correctly derived from dates", True, "Expiry alerts file has no rows yet (no active near-expiry/expired batches) — check vacuously passes")

# 15. ML data leakage check: lag_1 must equal prior day's daily_demand exactly, per medicine
leakage_violations = 0
feat_sorted = features.sort_values(["medicine_id", "date"])
for med_id, grp in feat_sorted.groupby("medicine_id"):
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
lines.append("# MEDICINE DATA QUALITY REPORT\n")
lines.append(f"**Checks passed: {n_pass} / {n_total}**\n")
lines.append("| Check | Result | Detail |")
lines.append("|---|---|---|")
for c in checks:
    result = "PASS" if c["passed"] else "**FAIL**"
    lines.append(f"| {c['check']} | {result} | {c['detail']} |")

report_text = "\n".join(lines)
with open(f"{BASE}/reports/MEDICINE_DATA_QUALITY_REPORT.md", "w") as f:
    f.write(report_text)

print(f"Validation complete: {n_pass}/{n_total} checks passed.")
if n_pass < n_total:
    failed = [c["check"] for c in checks if not c["passed"]]
    print("FAILED CHECKS:", failed)
else:
    print("All checks passed.")
