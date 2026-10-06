This folder is intentionally empty.

The project brief for this module references a real blood donation/
collection dataset with columns similar to:
    date, blood_type, donation_volume, data_type

That file was NOT provided when this pipeline was built, so no file was
fabricated here under the name "REAL" (fabricating real-world data is
explicitly disallowed by the project rules).

A structurally identical SYNTHETIC placeholder was generated instead, at:
    ../synthetic/blood_collection_SYNTHETIC_placeholder.csv

TO ACTIVATE REAL DATA:
1. Place your real file here as: blood_collection_REAL.csv
2. Ensure it has columns: date, blood_type, donation_volume, data_type
3. Update generate_blood_inventory.py to read from this file instead of
   the synthetic placeholder (see the "units_received" section).
4. Re-run the pipeline: generate_blood_inventory.py -> feature_engineering.py
   -> train_blood_models.py -> generate_recommendations_and_alerts.py
   -> validate_blood_data.py
5. Update BLOOD_DATA_REPORT.md and BLOOD_DATA_DICTIONARY.md to reflect
   the real provenance.
