# MEDICINE MODULE — DATA REPORT

Part of: *Integrated Medicine and Blood Management with Demand Prediction Using Machine Learning*

## 1. Purpose

This module predicts future medicine demand (medicine-wise and time-based),
compares predicted demand against inventory, tracks batch expiry, and
produces recommendations and alerts for the pharmacist. Geographic
analysis is explicitly out of scope and does not appear anywhere in this
pipeline.

## 2. Data Provenance — Real vs. Synthetic

**No real medicine master or transaction files were uploaded to this
pipeline run.** The specification calls for a real medicine master/catalog
and, where available, real transaction data — but only the specification
text was provided, not the underlying files. Consistent with the project's
own rule against fabricating and mislabeling real-world data, this pipeline
does **not** contain any file named `*_REAL.csv`.

| Dataset | Provenance | Notes |
|---|---|---|
| `synthetic/medicine_master_SYNTHETIC_placeholder.csv` | **SYNTHETIC (placeholder)** | 20 illustrative medicines with category/manufacturer/dosage_form/pack_size labels. Not sourced from any real pharmacy or hospital catalog. |
| `synthetic/medicine_demand_SYNTHETIC.csv` | **SYNTHETIC** | Generated because no real transaction/sales dataset with sufficient medicine-wise demand detail was available. Main demand variable: `units_requested`. |
| `synthetic/medicine_inventory_SYNTHETIC.csv` | **SYNTHETIC** | Derived logically from synthetic demand (`units_issued`); `units_received` is a modeled restocking proxy, not real procurement data. |
| `synthetic/medicine_batches_SYNTHETIC.csv` | **SYNTHETIC** | Batch/expiry records derived from the synthetic inventory receipt simulation and documented shelf-life assumptions by dosage form. |
| `ml/*.csv` | **Derived** | Model outputs from real, executed training runs on the synthetic datasets (no fabricated metrics). |
| `recommendations/*.csv`, `alerts/*.csv`, `expiry/*.csv` | **Derived** | Computed from actual calculated conditions (stock thresholds, predicted demand, trend, anomaly, expiry status). |

**No real patient, pharmacy, or transaction records exist anywhere in this
pipeline.** No file in this delivery should be described as actual
hospital/pharmacy data.

### Action required to activate real data

When the real medicine master and/or transaction files become available:

1. Place them at `medicine_data/real/medicine_master_REAL.csv` and, if
   applicable, `medicine_data/real/medicine_transactions_REAL.csv`.
2. Before treating any transaction column as "demand," confirm what the
   source actually measures (requests, dispensing, sales, stock movements
   are not interchangeable) and document it.
3. Update `standardize_medicine_data.py` to read from the real master
   file's `medicine_id` values instead of the placeholder catalog.
4. Re-run the pipeline in order (see Section 5).

## 3. Demand vs. Inventory vs. Batch/Expiry — Kept Separate

- **DEMAND**: `units_requested` (synthetic; documented as quantity requested at the pharmacy/ward level).
- **INVENTORY**: `opening_stock`, `units_received`, `units_issued`, `units_adjusted`, `closing_stock`.
- **BATCH/EXPIRY**: `manufacturing_date`, `expiry_date`, `units_remaining`, `expiry_status`.

These are never merged or renamed into one another.

## 4. Time-Based, Medicine-Wise Analysis Only

Analysis is performed by **date**, `medicine_id`, `medicine_name`, and
`category` only. No state/district/city/hospital-location columns exist in
any output file.

## 5. Pipeline / Script Execution Order

1. `standardize_medicine_data.py` → synthetic placeholder catalog
2. `generate_medicine_demand.py` → synthetic demand
3. `generate_medicine_inventory.py` → synthetic inventory
4. `generate_medicine_batches.py` → synthetic batches + expiry alerts
5. `feature_engineering.py` → daily/weekly/monthly/yearly aggregates, ML features, volume tiers, anomalies, trend, seasonality
6. `train_medicine_models.py` → model comparison + actual vs predicted
7. `generate_recommendations_and_alerts.py` → recommendations + alerts
8. `validate_medicine_data.py` → quality checks + `MEDICINE_DATA_QUALITY_REPORT.md`

## 6. Feature Engineering Notes

All rolling/lag features use `shift(1)` before windowing so no feature for
day *t* uses day *t*'s own demand value. Trend direction is derived from a
whole-history linear fit per medicine, compared against a documented ±5%
relative-change threshold (see `MEDICINE_DATA_DICTIONARY.md`).

## 7. Reproducibility

Fixed random seeds: demand generation `SEED=55`, inventory `SEED=321`,
batch/expiry `SEED=999`. Re-running the scripts in order reproduces
identical outputs.

## 8. Known Limitations

- The medicine catalog, demand, inventory, and batch data are all
  synthetic; no real observations back any figure in this module yet.
- `medicine_batches_SYNTHETIC.csv` and `medicine_expiry_alerts_SYNTHETIC.csv`
  now include genuine Expired and Near Expiry entries. These come from a
  documented, disclosed rule (a fixed 4% "reserve" fraction per batch that
  is never issued through normal FIFO dispensing, modeling real-world
  shrinkage/quarantine/hard-to-reach stock, plus a 60-day post-expiry
  disposal-grace window before write-off) rather than from randomly
  assigned or fabricated expiry labels — see `MEDICINE_DATA_DICTIONARY.md`.
- `units_received` in the inventory dataset is a modeled restocking proxy,
  not real procurement data, since no real receiving/purchase data was
  available.
- One-day-ahead demand forecasting only; multi-day horizons were not
  evaluated.
