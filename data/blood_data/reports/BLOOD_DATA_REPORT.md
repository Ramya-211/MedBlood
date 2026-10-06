# BLOOD MODULE — DATA REPORT

Part of: *Integrated Medicine and Blood Management with Demand Prediction Using Machine Learning*

## 1. Purpose

This module predicts future PATIENT DEMAND for blood units (by blood group,
Rh type, and blood component), compares predicted demand against available
inventory, and produces recommendations and alerts. Geographic analysis
(state/district/city/hospital-location) is explicitly **out of scope** and
is not present anywhere in this pipeline.

## 2. Data Provenance — Real vs. Synthetic

| Dataset | Provenance | Notes |
|---|---|---|
| `synthetic/blood_patient_demand_SYNTHETIC.csv` | **SYNTHETIC** | Generated because no real patient-request dataset was available. Main demand variable: `units_requested`. |
| `synthetic/blood_collection_SYNTHETIC_placeholder.csv` | **SYNTHETIC (placeholder)** | The project brief describes a real donation/collection dataset, but **no such file was uploaded to this pipeline run**. A structurally identical synthetic placeholder was generated instead so the supply-side pipeline can be exercised end-to-end. It must be replaced with the real file (`real/blood_collection_REAL.csv`, columns: `date, blood_type, donation_volume, data_type`) before any real-world conclusions are drawn. |
| `synthetic/blood_inventory_SYNTHETIC.csv` | **SYNTHETIC** | Derived logically from synthetic demand (`units_issued`) and a synthetic supply proxy. Not real stock data. |
| `synthetic/blood_batches_SYNTHETIC.csv` | **SYNTHETIC** | Batch/expiry records derived from the synthetic inventory simulation. |
| `ml/*.csv` | **Derived** | Model outputs computed from the synthetic datasets above using real, executed model training (no fabricated metrics). |
| `recommendations/*.csv`, `alerts/*.csv` | **Derived** | Computed from actual calculated conditions (stock thresholds, predicted demand, trend, anomaly, expiry). |

**No real patient records exist anywhere in this pipeline.** No file in this
delivery should be described as actual Indian/Telangana hospital data.

## 3. Demand vs. Supply vs. Inventory — Kept Separate

- **PATIENT DEMAND**: `units_requested` (from the synthetic patient demand dataset). This is the ML target.
- **SUPPLY/COLLECTION**: `donation_volume` (from the collection dataset — currently the SYNTHETIC placeholder, pending the real file).
- **INVENTORY**: `opening_stock`, `units_received`, `units_issued`, `units_discarded`, `units_expired`, `closing_stock`.

`donation_volume` is never used as, renamed to, or merged into `units_requested`
anywhere in this pipeline.

## 4. Time-Based Analysis Only

Analysis is performed by **date**, `blood_group`, `rh_type`, and
`blood_component` only. No state/district/city/hospital-location columns
exist in any output file.

## 5. File Structure

See `blood_data/` directory tree. Scripts run in this order:

1. `generate_blood_demand.py` → synthetic patient demand
2. `generate_blood_collection_placeholder.py` → synthetic supply placeholder (replace with real data when available)
3. `generate_blood_inventory.py` → synthetic inventory + batches
4. `feature_engineering.py` → time aggregates + ML features
5. `train_blood_models.py` → model comparison + actual vs predicted
6. `generate_recommendations_and_alerts.py` → recommendations + alerts
7. `validate_blood_data.py` → quality checks + `BLOOD_DATA_QUALITY_REPORT.md`

## 6. Reproducibility

All synthetic generation uses fixed random seeds (`SEED = 42` for demand,
`SEED = 7` for the collection placeholder, `SEED = 123` for inventory).
Re-running the scripts in order reproduces identical output files.

## 7. Known Limitation

The single largest limitation of this delivery is the **absence of the real
donation/collection dataset**. Supply-side figures and any inventory
conclusions drawn from `units_received` are currently illustrative
(synthetic) and should be re-validated once real collection data is
supplied.
