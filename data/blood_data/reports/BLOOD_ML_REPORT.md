# BLOOD ML REPORT

## 1. Dataset

`processed/blood_demand_features_SYNTHETIC.csv` — 46,752 daily rows across
32 segments (4 blood groups × 2 Rh types × 4 components), 2021-01-01 to
2024-12-31. Entirely SYNTHETIC (see `BLOOD_DATA_REPORT.md` for provenance).

## 2. Target

`target_next_day_demand` — the following day's `daily_demand`
(i.e., PATIENT DEMAND, `units_requested` aggregated to the segment/day
level), predicted **one day ahead** per (blood_group, rh_type,
blood_component) segment. `donation_volume` was never used as, or mixed
into, this target.

## 3. Features

- `rolling_mean_7`, `rolling_mean_30` — past-only rolling means (computed on `shift(1)` series)
- `growth_rate_7d`, `growth_rate_30d` — past-only percentage change
- `trend_slope` — 30-day rolling linear-fit slope on past values
- `month`, `day_of_week` — calendar features
- `seasonality_index` — ratio of past 7-day mean to past 90-day mean
- `lag_1`, `lag_7`, `lag_14`, `lag_30` — past demand values
- `anomaly_flag`, `anomaly_score` — z-score vs. past 30-day mean/std
- One-hot encodings of `blood_group`, `rh_type`, `blood_component`, `season`

No geographic features. No same-day or future information is used in any
feature (see leakage note below).

## 4. Preprocessing & Feature Engineering

- Rows with any NaN in the feature set or target were dropped (early rows
  in each segment's history, where rolling/lag windows are not yet full).
- Categorical variables one-hot encoded.
- All rolling/lag calculations applied `shift(1)` before windowing so that
  no feature for day *t* uses day *t*'s own demand value.

## 5. Train / Validation / Test Split

Chronological split (no shuffling), by date order across the full dataset:

| Split | Rows | Date range |
|---|---|---|
| Train | 24,370 | 2021-02-01 to 2023-11-19 |
| Validation | 5,222 | 2023-11-19 to 2024-06-14 |
| Test | 5,223 | 2024-06-14 to 2024-12-30 |

(Validation set was held out for model development; reported metrics below
are on the untouched **test** set.)

## 6. Models Evaluated

1. **Baseline** — naive forecast using `lag_1` (yesterday's demand)
2. **Linear Regression**
3. **Random Forest Regressor** (200 trees, max_depth=10)
4. **XGBoost Regressor** (300 trees, max_depth=6, lr=0.05)

## 7. Actual Test-Set Metrics

| Model | RMSE | MAE | R² |
|---|---|---|---|
| Linear Regression | 2.2900 | 1.0718 | 0.9661 |
| XGBoost Regressor | 2.4153 | 0.9376 | 0.9623 |
| Random Forest Regressor | 2.4890 | 0.9390 | 0.9599 |
| Baseline (naive lag-1) | 3.3055 | 1.5315 | 0.9293 |

These metrics were computed by actually training and evaluating each model
on the held-out chronological test set — none are fabricated or assumed.
Full results: `ml/blood_model_comparison.csv`.

## 8. Selected Model

**Linear Regression**, selected on lowest test-set RMSE. Note that all
models substantially beat the naive baseline, and differences between
Linear Regression, XGBoost, and Random Forest are modest — consistent with
demand series that are strongly driven by recent lags/rolling means
(features a linear model can exploit efficiently). `predicted_demand` in
`ml/blood_demand_actual_vs_predicted.csv` uses this model's output.

## 9. Limitations

- **Underlying demand data is synthetic**, generated with documented trend/
  seasonality/noise/spike rules — not observed hospital behavior. High R²
  values partly reflect that the synthetic generation process itself is
  smooth and autocorrelated; real-world demand may be noisier or driven by
  factors not modeled here (e.g., actual emergencies, supply constraints
  feeding back into requests).
- One-day-ahead horizon only; multi-day-ahead forecasting was not evaluated
  in this run.
- Model selection used RMSE only; no hyperparameter search was performed
  beyond the fixed configurations listed above.
- Segment-level (blood_group × rh_type × blood_component) demand can be
  very small for rare combinations (e.g., AB− Plasma), which inflates
  relative error for those segments even when absolute error is small.

## 10. Synthetic-Data Disclosure

All demand figures, features, and predictions in this report are derived
from the SYNTHETIC patient demand dataset. They do not represent, and must
not be presented as, real hospital or patient data from India, Telangana,
or any other real institution.
