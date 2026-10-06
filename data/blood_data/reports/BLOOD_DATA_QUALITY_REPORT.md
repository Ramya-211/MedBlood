# BLOOD DATA QUALITY REPORT

**Checks passed: 26 / 26**

| Check | Result | Detail |
|---|---|---|
| No duplicate record_id in demand | PASS |  |
| No duplicate inventory_id in inventory | PASS |  |
| No duplicate batch_id in batches | PASS |  |
| No duplicate demand records (date+segment) | PASS | 0 duplicates found |
| No duplicate inventory records (date+segment) | PASS | 0 duplicates found |
| No missing values in demand dataset | PASS | 0 missing cells |
| No missing values in inventory dataset | PASS | 0 missing cells |
| No missing values in batches dataset | PASS | 0 missing cells |
| All blood_group values valid (demand) | PASS |  |
| All rh_type values valid (demand) | PASS |  |
| All blood_component values valid (demand) | PASS |  |
| All expiry_status values valid (batches) | PASS |  |
| No negative values in demand dataset | PASS |  |
| No negative values in inventory dataset | PASS |  |
| No null dates in demand | PASS |  |
| No null dates in inventory | PASS |  |
| No expiry_date before collection_date | PASS | 0 violations |
| emergency_requests + routine_requests == units_requested (all rows) | PASS | 0 mismatches |
| units_issued never exceeds units_requested | PASS | 0 violations |
| units_transfused never exceeds units_issued | PASS | 0 violations |
| No negative closing_stock | PASS | 0 violations |
| Inventory equation holds for all rows | PASS | 0 violations |
| Stock continuity holds (next opening == prev closing) | PASS | 0 violations |
| expiry_date strictly after collection_date | PASS |  |
| expiry_status correctly derived from dates | PASS | 0 mismatches |
| lag_1 feature correctly reflects prior day only (no leakage) | PASS | 0 violations |