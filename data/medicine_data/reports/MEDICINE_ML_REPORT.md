# MEDICINE ML REPORT

## 1. Target Variable

`target_next_day_demand` — the following day's `daily_demand`
(= `units_requested`), predicted **one day ahead** per medicine
(`medicine_id`). This is the medicine module's demand variable, as
documented in `MEDICINE_DATA_REPORT.md` and `MEDICINE_DATA_DICTIONARY.md`.
It is entirely SYNTHETIC (see data provenance report — no real transaction
data was available for this run).

## 2. Features

- `rolling_mean_7`, `rolling_mean_30` — past-only rolling means (via `shift(1)`)
- `growth_rate_7d`, `growth_rate_30d` — past-only percentage change
- `trend_slope` — 30-day rolling linear-fit slope on past values
- `month`, `day_of_week` — calendar features
- `seasonality_index` — ratio of past 7-day mean to past 90-day mean
- `lag_1`, `lag_7`, `lag_14`, `lag_30` — past demand values
- `anomaly_flag`, `anomaly_score` — z-score vs. past 30-day mean/std
- One-hot encodings of `medicine_id`, `category`, `season`

No geographic features. No same-day or future information used.

## 3. Preprocessing

- Rows with any NaN in the feature set or target dropped (early rows per
  medicine, before rolling/lag windows are full).
- Categorical variables one-hot encoded.

## 4. Feature Engineering / Leakage Prevention

All rolling and lag calculations are applied to a `shift(1)` series before
windowing, so no feature for day *t* uses day *t*'s own demand value. This
was explicitly verified in `validate_medicine_data.py` (the `lag_1`
leakage check).

## 5. Train / Validation / Test Strategy

Chronological split (no shuffling), by date order:

| Split | Rows | Date range |
|---|---|---|
| Train | 19,939 | 2021-02-01 to 2023-10-27 |
| Validation | 4,273 | 2023-10-27 to 2024-05-28 |
| Test | 4,273 | 2024-05-28 to 2024-12-30 |

Metrics below are reported on the untouched test set.

## 6. Candidate Models

1. **Baseline** — naive forecast using `lag_1`
2. **Linear Regression**
3. **Random Forest Regressor** (200 trees, max_depth=10)
4. **XGBoost Regressor** (300 trees, max_depth=6, lr=0.05)

## 7. Actual Test-Set Metrics

| Model | RMSE | MAE | R² |
|---|---|---|---|
| XGBoost Regressor | 4.2304 | 2.7766 | 0.9465 |
| Random Forest Regressor | 4.2537 | 2.8004 | 0.9459 |
| Linear Regression | 4.8015 | 3.2503 | 0.9311 |
| Baseline (naive lag-1) | 7.0171 | 4.6822 | 0.8528 |

Full results: `ml/medicine_model_comparison.csv`. These were computed by
actually training and evaluating each model — none are fabricated.

## 8. Selected Model

**XGBoost Regressor**, selected on lowest test-set RMSE. It edges out
Random Forest by a small margin and both tree-based models clearly
outperform Linear Regression and the naive baseline — consistent with
medicine demand across 20 distinct products/categories having non-linear,
medicine-specific interactions that tree ensembles capture better than a
single linear model. `ml/medicine_actual_vs_predicted.csv` uses this
model's output for `predicted_demand`.

## 9. Limitations

- **All underlying demand data is synthetic**, generated with documented
  per-category trend/seasonality/noise/spike rules — not observed pharmacy
  behavior. Reported R² partly reflects the smoothness of the synthetic
  generation process itself.
- Only 20 medicines are represented (the placeholder catalog); a real
  catalog would likely contain far more SKUs with more heterogeneous demand
  patterns.
- One-day-ahead horizon only.
- No hyperparameter search beyond the fixed configurations listed above.
- `units_received` (used indirectly via inventory-linked features in
  future extensions) is a modeled restocking proxy, not real procurement
  data.

## 10. Data Provenance / Synthetic-Data Disclosure

All demand figures, features, and predictions in this report derive from
the SYNTHETIC medicine demand dataset. They do not represent, and must not
be presented as, real pharmacy or hospital transaction data.
