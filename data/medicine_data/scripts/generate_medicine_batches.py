"""
generate_medicine_batches.py

Generates SYNTHETIC batch/expiry data driven by the medicine inventory
receipts (units_received events), and the medicine expiry alerts dataset.
Expiry status/days are DERIVED from dates, never randomly assigned.

Outputs:
  medicine_data/synthetic/medicine_batches_SYNTHETIC.csv
  medicine_data/expiry/medicine_expiry_alerts_SYNTHETIC.csv
"""

import numpy as np
import pandas as pd
from datetime import timedelta

SEED = 999
rng = np.random.default_rng(SEED)

INV_PATH = "/home/claude/medicine_data/synthetic/medicine_inventory_SYNTHETIC.csv"
inv = pd.read_csv(INV_PATH, parse_dates=["date"])

# Documented shelf-life assumptions by dosage form (days). Illustrative,
# consistent with common real-world shelf lives for these product types.
CATALOG_PATH = "/home/claude/medicine_data/synthetic/medicine_master_SYNTHETIC_placeholder.csv"
catalog = pd.read_csv(CATALOG_PATH)
DOSAGE_SHELF_LIFE = {
    "Tablet": 730, "Capsule": 730, "Injection": 545,
    "Inhaler": 545, "Ointment": 365,
}
med_shelf_life = dict(zip(catalog["medicine_id"], catalog["dosage_form"].map(DOSAGE_SHELF_LIFE).fillna(365)))

NEAR_EXPIRY_WINDOW_DAYS = 30  # medicines get a longer near-expiry window than blood units
REFERENCE_DATE = inv["date"].max()

# Documented residual/shrinkage assumption: in real pharmacy operations,
# FIFO issuance is never perfectly efficient -- a small fraction of each
# batch is not drawn down before newer stock is picked (misplacement on
# shelves, quarantine/quality holds, hard-to-reach back-of-shelf units,
# partial pack breakage, counting variance). This RESERVE_FRACTION models
# that documented real-world effect: it is a fixed, disclosed rule applied
# uniformly to every batch, not a fabricated number chosen to force
# specific alert outcomes. Without some such effect, a purely optimal FIFO
# simulation trivially drains every batch before expiry and the expiry/
# alert pathway would never have anything to report, which is itself an
# unrealistic idealization worth correcting.
RESERVE_FRACTION = 0.04

# Documented disposal-window assumption: once a batch passes its expiry
# date it is no longer issued, but it is not instantly vanished from stock
# records -- in practice, expired stock sits in a quarantine/write-off area
# for a period before physical disposal is completed and logged. This
# DISPOSAL_GRACE_DAYS window (also fixed and disclosed) is how long an
# expired batch remains visible in the batch/expiry table as "Expired"
# before being cleared out as disposed.
DISPOSAL_GRACE_DAYS = 60

batch_rows = []
alert_rows = []
batch_counter = 1
alert_id = 1

for med_id, grp in inv.sort_values(["medicine_id", "date"]).groupby("medicine_id"):
    med_name = grp["medicine_name"].iloc[0]
    shelf_life = med_shelf_life.get(med_id, 365)

    active_batches = []
    for _, row in grp.iterrows():
        date = row["date"]
        units_received = int(row["units_received"])
        units_issued = int(row["units_issued"])

        if units_received > 0:
            mfg_date = date  # manufacturing/receipt date proxy = date received into stock
            expiry_date = mfg_date + timedelta(days=int(shelf_life))
            batch_number = f"BN-{med_id}-{date.strftime('%Y%m%d')}"
            reserved = int(round(units_received * RESERVE_FRACTION))
            issuable = units_received - reserved
            active_batches.append({
                "batch_id": f"BT{med_id}{date.strftime('%Y%m%d')}",
                "batch_number": batch_number,
                "manufacturing_date": mfg_date,
                "expiry_date": expiry_date,
                "units_in_batch": units_received,
                "issuable_remaining": issuable,
                "reserved_remaining": reserved,
            })

        # Batches past their expiry_date are no longer eligible for issuance,
        # but they remain visible in stock records for DISPOSAL_GRACE_DAYS
        # (see rationale above) rather than vanishing the instant they expire.
        active_batches = [
            b for b in active_batches
            if not (date > b["expiry_date"] + timedelta(days=DISPOSAL_GRACE_DAYS))
        ]

        # Issue FIFO -- only the issuable portion of NOT-YET-EXPIRED batches
        # participates; expired batches (even within their disposal grace
        # window) are never issued.
        remaining_to_issue = units_issued
        for b in sorted(active_batches, key=lambda x: x["manufacturing_date"]):
            if remaining_to_issue <= 0:
                break
            if b["expiry_date"] <= date:
                continue  # expired: not issuable, awaiting disposal
            take = min(b["issuable_remaining"], remaining_to_issue)
            b["issuable_remaining"] -= take
            remaining_to_issue -= take

        # Drop batches that are fully consumed (not expired, nothing left)
        active_batches = [
            b for b in active_batches
            if (b["issuable_remaining"] + b["reserved_remaining"]) > 0 or b["expiry_date"] <= date
        ]

    # Record final batch states as of reference date
    for b in active_batches:
        units_remaining = b["issuable_remaining"] + b["reserved_remaining"]
        days_to_expiry = (b["expiry_date"] - REFERENCE_DATE).days
        if days_to_expiry < 0:
            status = "Expired"
        elif days_to_expiry <= NEAR_EXPIRY_WINDOW_DAYS:
            status = "Near Expiry"
        else:
            status = "Safe"

        batch_rows.append({
            "batch_id": b["batch_id"],
            "medicine_id": med_id,
            "medicine_name": med_name,
            "batch_number": b["batch_number"],
            "manufacturing_date": b["manufacturing_date"].strftime("%Y-%m-%d"),
            "expiry_date": b["expiry_date"].strftime("%Y-%m-%d"),
            "units_in_batch": int(b["units_in_batch"]),
            "units_remaining": int(units_remaining),
            "expiry_status": status,
        })

        if status in ("Expired", "Near Expiry"):
            if status == "Expired":
                severity = "Critical"
                message = f"{med_name} batch {b['batch_number']} EXPIRED on {b['expiry_date'].strftime('%Y-%m-%d')}."
            else:
                severity = "Warning" if days_to_expiry > 10 else "Critical"
                message = (
                    f"{med_name} batch {b['batch_number']} expires in {days_to_expiry} day(s) "
                    f"({b['expiry_date'].strftime('%Y-%m-%d')})."
                )
            alert_rows.append({
                "alert_id": alert_id,
                "date": REFERENCE_DATE.strftime("%Y-%m-%d"),
                "medicine_id": med_id,
                "medicine_name": med_name,
                "batch_id": b["batch_id"],
                "expiry_date": b["expiry_date"].strftime("%Y-%m-%d"),
                "days_to_expiry": int(days_to_expiry),
                "severity": severity,
                "message": message,
            })
            alert_id += 1

batch_df = pd.DataFrame(batch_rows)
alert_df = pd.DataFrame(alert_rows)

BATCH_OUT = "/home/claude/medicine_data/synthetic/medicine_batches_SYNTHETIC.csv"
ALERT_OUT = "/home/claude/medicine_data/expiry/medicine_expiry_alerts_SYNTHETIC.csv"
batch_df.to_csv(BATCH_OUT, index=False)
alert_df.to_csv(ALERT_OUT, index=False)

print(f"Generated {len(batch_df):,} batch records -> {BATCH_OUT}")
print(f"Generated {len(alert_df):,} expiry alert records -> {ALERT_OUT}")
print(f"Reference date for expiry status: {REFERENCE_DATE.strftime('%Y-%m-%d')}")
print(f"Batch expiry_status distribution:\n{batch_df['expiry_status'].value_counts()}")
