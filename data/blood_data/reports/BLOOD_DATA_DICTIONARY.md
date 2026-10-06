# BLOOD DATA DICTIONARY

Legend: **Source** = REAL or SYNTHETIC. **Type** = RAW (directly generated/collected) or DERIVED (computed from other columns).

## `synthetic/blood_patient_demand_SYNTHETIC.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| record_id | integer | Unique row identifier | SYNTHETIC | Derived | Sequential, assigned after final sort |
| date | date | Calendar date of demand | SYNTHETIC | Raw | Daily series, 2021-01-01 to 2024-12-31 |
| blood_group | category (A/B/AB/O) | ABO blood group | SYNTHETIC | Raw | Sampled per segment |
| rh_type | category (Positive/Negative) | Rh factor | SYNTHETIC | Raw | Sampled per segment |
| blood_component | category | Whole Blood / RBC / Platelets / Plasma | SYNTHETIC | Raw | Sampled per segment |
| units_requested | integer ≥0 | **PATIENT DEMAND** — units requested by patients/hospitals | SYNTHETIC | Raw (generated) | Trend + seasonality + weekday effect + noise + spikes/lows, see `generate_blood_demand.py` |
| units_issued | integer ≥0 | Units actually issued against the request | SYNTHETIC | Derived | `= units_requested × fulfillment_rate`, capped at `units_requested` |
| units_transfused | integer ≥0 | Units actually transfused to patients | SYNTHETIC | Derived | `= units_issued × transfusion_rate`, capped at `units_issued` |
| emergency_requests | integer ≥0 | Portion of request that was emergency | SYNTHETIC | Derived | `= units_requested × emergency_ratio` |
| routine_requests | integer ≥0 | Portion of request that was routine | SYNTHETIC | Derived | `= units_requested − emergency_requests` |

## `synthetic/blood_collection_SYNTHETIC_placeholder.csv` — SYNTHETIC (placeholder for real data)

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| date | date | Collection date | SYNTHETIC | Raw | Daily series |
| blood_type | category | ABO+Rh combined (e.g. O+) | SYNTHETIC | Raw | 8 standard blood types |
| donation_volume | integer ≥0 | **SUPPLY/COLLECTION** — units donated/collected | SYNTHETIC | Raw (generated) | Base + trend + season + noise |
| data_type | string | Provenance flag | SYNTHETIC | Raw | Always `"SYNTHETIC_PLACEHOLDER"` — replace file with real data (`data_type` should reflect real provenance) when available |

> **This is NOT the real donation dataset.** No real file was provided to this pipeline run.

## `synthetic/blood_inventory_SYNTHETIC.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| inventory_id | integer | Unique row identifier | SYNTHETIC | Derived | Sequential |
| date | date | Inventory date | SYNTHETIC | Raw | Daily series |
| blood_group / rh_type / blood_component | category | Segment identifiers | SYNTHETIC | Raw | Same categories as demand dataset |
| opening_stock | integer ≥0 | Stock at start of day | SYNTHETIC | Derived | `= previous day's closing_stock` (continuity enforced) |
| units_received | integer ≥0 | Units received into stock | SYNTHETIC | Derived | Modeled from segment's recent issuance + noise (proxy for real supply; see disclosure) |
| units_issued | integer ≥0 | Units issued from stock (FIFO by batch) | SYNTHETIC | Derived | Capped by `units_requested`'s companion `units_issued` from demand dataset and available batch stock |
| units_discarded | integer ≥0 | Units discarded (wastage) | SYNTHETIC | Derived | ~1% binomial wastage rate on available stock |
| units_expired | integer ≥0 | Units expired that day | SYNTHETIC | Derived | Sum of batch `units_remaining` whose `expiry_date` ≤ current date |
| closing_stock | integer ≥0 | Stock at end of day | SYNTHETIC | Derived | `= opening_stock + units_received − units_issued − units_discarded − units_expired` (never negative) |

## `synthetic/blood_batches_SYNTHETIC.csv` — SYNTHETIC

| Column | Data Type | Meaning | Source | Raw/Derived | Rule |
|---|---|---|---|---|---|
| batch_id | string | Unique batch identifier | SYNTHETIC | Derived | `BT{group}{rh_initial}{component_code}{collection_date}` |
| collection_date | date | Date batch was created | SYNTHETIC | Raw | = date of corresponding `units_received` event |
| expiry_date | date | Date batch expires | SYNTHETIC | Derived | `collection_date + shelf_life_days` (Whole Blood 35d, RBC 42d, Platelets 5d, Plasma 365d) |
| blood_group / rh_type / blood_component | category | Segment identifiers | SYNTHETIC | Raw | — |
| units_in_batch | integer ≥0 | Units originally in the batch | SYNTHETIC | Raw | = `units_received` on collection date |
| units_remaining | integer ≥0 | Units left in the batch as of reference date | SYNTHETIC | Derived | Decremented by FIFO issuance/discard/expiry simulation |
| expiry_status | category | Expired / Near Expiry / Safe | SYNTHETIC | Derived | From `expiry_date` vs. reference date (max date in demand dataset); Near Expiry = expires within 5 days |

## `processed/blood_demand_{daily,weekly,monthly,yearly}_SYNTHETIC.csv` — SYNTHETIC (derived)

Aggregations of `daily_demand` (`= units_requested`) and related counts by `blood_group`, `rh_type`, `blood_component`, and the relevant time bucket. No geographic grouping.

## `processed/blood_demand_features_SYNTHETIC.csv` — SYNTHETIC (derived)

| Column | Meaning | Rule |
|---|---|---|
| daily_demand | Same-day demand (= units_requested) | Raw passthrough |
| weekly_demand / monthly_demand | Trailing 7-/30-day sum ending at current day | `rolling(7 or 30).sum()` |
| rolling_mean_7 / rolling_mean_30 | Past-only rolling mean | Computed on `shift(1)` series |
| growth_rate_7d / growth_rate_30d | Past-only % change | `(shifted_t − shifted_{t-n}) / shifted_{t-n}` |
| trend_slope | 30-day rolling linear-fit slope | `np.polyfit` on past 30 values |
| month / day_of_week / season | Calendar features | From `date` |
| seasonality_index | Relative seasonal elevation | `rolling_mean_7 / rolling_mean_90` (past-only) |
| lag_1 / lag_7 / lag_14 / lag_30 | Past demand values | `shift(n)` |
| anomaly_flag / anomaly_score | Anomaly detection | Z-score of current value vs past 30-day mean/std; flag if `|z| > 2.5` |

## `ml/blood_model_comparison.csv` — Derived (from real model training)

Columns: `model, RMSE, MAE, R2` — actual metrics from evaluating each model on the chronological test set. See `BLOOD_ML_REPORT.md`.

## `ml/blood_demand_actual_vs_predicted.csv` — Derived

| Column | Meaning | Source |
|---|---|---|
| actual_demand | True `daily_demand` (next-day) | From synthetic demand data |
| predicted_demand | Model's prediction | From the selected model (Linear Regression) |
| prediction_error | `actual_demand − predicted_demand` | Derived |

## `recommendations/blood_recommendations_SYNTHETIC.csv` and `alerts/blood_alerts_SYNTHETIC.csv` — Derived

Generated from actual calculated conditions: predicted demand vs. current stock, stock-status thresholds (Critical <2 days cover, Low <5 days, Overstock >30 days), 7-day demand growth rate, anomaly flag, and batch expiry status. See `generate_recommendations_and_alerts.py` for exact thresholds and logic.
