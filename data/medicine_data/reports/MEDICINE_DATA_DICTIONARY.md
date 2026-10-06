# MEDICINE DATA DICTIONARY

Legend: **Source** = REAL / DERIVED FROM REAL / SYNTHETIC. **Type** = RAW or DERIVED.

> **Provenance summary:** No real medicine master or transaction files were
> uploaded to this pipeline run. Every dataset below is either SYNTHETIC or
> DERIVED from a synthetic dataset. None represents actual hospital,
> pharmacy, or patient data. See `MEDICINE_DATA_REPORT.md` for full
> disclosure and instructions for activating real data.

## `synthetic/medicine_master_SYNTHETIC_placeholder.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| medicine_id | string | Unique medicine identifier | SYNTHETIC | Raw | Assigned sequentially (MED001…MED020) |
| medicine_name | string | Medicine display name (incl. strength) | SYNTHETIC | Raw | Illustrative name, not from a real catalog |
| composition | string | Active ingredient(s) | SYNTHETIC | Raw | Illustrative, matches common generic names |
| manufacturer | string | Manufacturer label | SYNTHETIC | Raw | Placeholder label ("Generic Pharma A/B/C/D") |
| dosage_form | string | Tablet/Capsule/Injection/Inhaler/Ointment | SYNTHETIC | Raw | Illustrative |
| pack_size | string | Pack size descriptor | SYNTHETIC | Raw | Illustrative |
| category | string | Therapeutic category | SYNTHETIC | Raw | Illustrative |
| provenance | string | Explicit provenance flag | SYNTHETIC | Raw | Always `"SYNTHETIC_PLACEHOLDER"` |

## `synthetic/medicine_demand_SYNTHETIC.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| record_id | integer | Unique row identifier | SYNTHETIC | Derived | Sequential after final sort |
| date | date | Calendar date of demand | SYNTHETIC | Raw | Daily series, 2021-01-01 to 2024-12-31 |
| medicine_id | string | FK to catalog | SYNTHETIC | Raw | — |
| medicine_name | string | Medicine name | SYNTHETIC | Raw | Copied from catalog |
| category | string | Therapeutic category | SYNTHETIC | Raw | Copied from catalog |
| units_requested | integer ≥0 | **DEMAND** — units requested at pharmacy/ward level | SYNTHETIC | Raw (generated) | Category base + trend + seasonal phase + weekday effect + noise + spikes/drops; see `generate_medicine_demand.py` |
| units_issued | integer ≥0 | Units issued against the request | SYNTHETIC | Derived | `= units_requested × fulfillment_rate`, capped at `units_requested` |
| units_dispensed | integer ≥0 | Units actually dispensed to patient | SYNTHETIC | Derived | `= units_issued × dispense_rate`, capped at `units_issued` |

## `synthetic/medicine_inventory_SYNTHETIC.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| inventory_id | integer | Unique row identifier | SYNTHETIC | Derived | Sequential |
| date | date | Inventory date | SYNTHETIC | Raw | Daily series |
| medicine_id / medicine_name | — | Medicine identifiers | SYNTHETIC | Raw | — |
| opening_stock | integer ≥0 | Stock at start of day | SYNTHETIC | Derived | `= previous day's closing_stock` (continuity enforced) |
| units_received | integer ≥0 | Units received into stock | SYNTHETIC | Derived | Modeled restock proxy: rolling avg of recent issuance × noise, applied every ~5th day (lumpy restocking) |
| units_issued | integer ≥0 | Units issued from stock | SYNTHETIC | Derived | Capped by available stock (`opening_stock + units_received`) |
| units_adjusted | integer | Manual stock adjustment (audit/damage correction) | SYNTHETIC | Derived | ~3% daily probability of a small ±1% adjustment; can be negative |
| closing_stock | integer ≥0 | Stock at end of day | SYNTHETIC | Derived | `= opening_stock + units_received − units_issued + units_adjusted` (never negative) |
| stock_status | category | Critical / Low / Normal / Overstock | SYNTHETIC | Derived | Days-of-cover (`closing_stock / avg_daily_issuance_30d`): Critical <3 days, Low <7 days, Overstock >45 days, else Normal |

## `synthetic/medicine_batches_SYNTHETIC.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| batch_id | string | Unique batch identifier | SYNTHETIC | Derived | `BT{medicine_id}{receipt_date}` |
| medicine_id / medicine_name | — | Medicine identifiers | SYNTHETIC | Raw | — |
| batch_number | string | Human-readable batch number | SYNTHETIC | Derived | `BN-{medicine_id}-{receipt_date}` |
| manufacturing_date | date | Batch creation date | SYNTHETIC | Raw | = date of corresponding `units_received` event (proxy; no real manufacturing date exists) |
| expiry_date | date | Batch expiry date | SYNTHETIC | Derived | `manufacturing_date + shelf_life_days`, by dosage form: Tablet/Capsule 730d, Injection/Inhaler 545d, Ointment 365d |
| units_in_batch | integer ≥0 | Units originally received | SYNTHETIC | Raw | = `units_received` on that date |
| units_remaining | integer ≥0 | Units left as of reference date | SYNTHETIC | Derived | FIFO issuance simulation, with a documented 4% "reserve" fraction per batch that is never issued (models real-world shrinkage/quarantine/hard-to-reach stock — see `MEDICINE_DATA_REPORT.md` §8) |
| expiry_status | category | Expired / Near Expiry / Safe | SYNTHETIC | Derived | From `expiry_date` vs. reference date (max date in demand dataset); Near Expiry = expires within 30 days; expired batches remain visible for a documented 60-day disposal-grace window before being cleared as written off |

## `processed/medicine_demand_{daily,weekly,monthly,yearly}.csv` — Derived (from synthetic)

Aggregations of `daily_demand` (`= units_requested`) and related counts by `medicine_id`, `medicine_name`, `category`, and the relevant time bucket. No geographic grouping.

## `processed/medicine_demand_features.csv` — Derived (from synthetic)

| Column | Meaning | Rule |
|---|---|---|
| daily_demand | Same-day demand | Raw passthrough |
| weekly_demand / monthly_demand | Trailing 7-/30-day sum ending at current day | `rolling(7 or 30).sum()` |
| rolling_mean_7 / rolling_mean_30 | Past-only rolling mean | On `shift(1)` series |
| growth_rate_7d / growth_rate_30d | Past-only % change | `(shifted_t − shifted_{t-n}) / shifted_{t-n}` |
| trend_slope | 30-day rolling linear-fit slope | `np.polyfit` on past 30 values |
| month / day_of_week / season | Calendar features | From `date` |
| seasonality_index | Relative seasonal elevation | `rolling_mean_7 / rolling_mean_90` (past-only) |
| lag_1 / lag_7 / lag_14 / lag_30 | Past demand values | `shift(n)` |
| anomaly_flag / anomaly_score | Anomaly detection | Z-score of current value vs. past 30-day mean/std; flag if `|z| > 2.5` |

## `processed/medicine_volume_tiers.csv` — Derived (from synthetic)

| Column | Meaning | Rule |
|---|---|---|
| total_units_dispensed | Sum of `units_dispensed` over the full period | Aggregated from demand dataset |
| volume_tier | Fast / Medium / Slow Moving | Medicines ranked by `total_units_dispensed`; top third = Fast Moving, middle third = Medium Moving, bottom third = Slow Moving. This is a **medicine-level** classification (supported because per-medicine daily demand exists for all 20 catalog medicines). |

## `processed/medicine_demand_anomalies.csv` — Derived (from synthetic)

Row-level export of every date/medicine combination where `anomaly_flag == 1` in the features dataset. `anomaly_type` = "Demand Spike" if `anomaly_score > 0`, else "Demand Drop". Calculated, not manually labeled.

## `processed/medicine_trend_analysis.csv` — Derived (from synthetic)

| Column | Meaning | Rule |
|---|---|---|
| trend_slope | Whole-history linear-fit slope of daily demand vs. day index | `np.polyfit` over the full series per medicine |
| trend_direction | Increasing / Decreasing / Stable | Implied total change (`slope × n_days`) as a fraction of mean demand: >+5% → Increasing, <−5% → Decreasing, else Stable |
| growth_rate_7d / growth_rate_30d | Average of the daily feature-level growth rates | Mean of `growth_rate_7d` / `growth_rate_30d` from the features dataset |

## `processed/medicine_seasonality.csv` — Derived (from synthetic)

Medicine × month summary of average `seasonality_index` (from the features dataset), with the corresponding `season` label. Calculated, not fabricated.

## `ml/medicine_model_comparison.csv` — Derived (from real model training)

Columns: `model, RMSE, MAE, R2` — actual metrics from evaluating each model on the chronological test set. See `MEDICINE_ML_REPORT.md`.

## `ml/medicine_actual_vs_predicted.csv` — Derived

| Column | Meaning | Source |
|---|---|---|
| actual_demand | True next-day `daily_demand` | From synthetic demand data |
| predicted_demand | Model's prediction | From the selected model (XGBoost Regressor) |
| prediction_error | `actual_demand − predicted_demand` | Derived |

## `expiry/medicine_expiry_alerts_SYNTHETIC.csv` — Derived (from synthetic)

| Column | Meaning | Rule |
|---|---|---|
| days_to_expiry | Days between reference date and batch expiry | `expiry_date − reference_date`, in days (negative for already-expired batches) |
| severity | Info / Warning / Critical | Expired → Critical; Near Expiry with ≤10 days → Critical, else Warning |

380 rows as of this run: 240 Expired, 140 Near Expiry, all linked to real rows in `medicine_batches_SYNTHETIC.csv` by `batch_id`.

## `recommendations/medicine_recommendations_SYNTHETIC.csv` and `alerts/medicine_alerts_SYNTHETIC.csv` — Derived

Generated from actual calculated conditions: predicted demand vs. current stock, `stock_status` thresholds, `trend_direction`/`growth_rate_7d`, `anomaly_flag`, and batch `expiry_status`. See `generate_recommendations_and_alerts.py` for exact logic.
