This folder is intentionally empty.

The project brief for this module references:
    medicine_master_REAL.csv          (medicine catalog)
    medicine_transactions_REAL.csv    (real sales/transaction data, if available)

Neither file was provided when this pipeline was built, so no file was
fabricated here under the "REAL" name (fabricating real-world data is
explicitly disallowed by the project rules).

A structurally similar SYNTHETIC placeholder catalog was generated instead,
at:
    ../synthetic/medicine_master_SYNTHETIC_placeholder.csv

TO ACTIVATE REAL DATA:
1. Place your real files here as:
   - medicine_master_REAL.csv (columns: medicine_id, medicine_name,
     composition, manufacturer, dosage_form, pack_size, category — only
     include fields actually present in your source)
   - medicine_transactions_REAL.csv, if you have real transaction/sales
     data (document exactly what the source measures before treating any
     column as "demand")
2. Update standardize_medicine_data.py to read from the real master file's
   medicine_id values instead of the placeholder catalog.
3. If medicine_transactions_REAL.csv provides sufficient medicine-wise
   demand detail, consider using it (or a documented transformation of it)
   in place of generate_medicine_demand.py's synthetic output. Otherwise,
   keep the synthetic demand generation but key it to the real medicine_id
   values.
4. Re-run the full pipeline in order: generate_medicine_demand.py ->
   generate_medicine_inventory.py -> generate_medicine_batches.py ->
   feature_engineering.py -> train_medicine_models.py ->
   generate_recommendations_and_alerts.py -> validate_medicine_data.py
5. Update MEDICINE_DATA_REPORT.md and MEDICINE_DATA_DICTIONARY.md to
   reflect the real provenance.
