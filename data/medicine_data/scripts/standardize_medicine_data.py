"""
standardize_medicine_data.py

PROVENANCE NOTE:
-----------------
The project brief calls for a REAL medicine master dataset (medicine_id,
medicine_name, composition, manufacturer, dosage_form, pack_size, category)
and, where available, REAL transaction/sales data.

Neither file was provided to this pipeline run. To avoid fabricating and
mislabeling real-world data (explicitly forbidden by the project rules),
this script does NOT create medicine_master_REAL.csv or
medicine_transactions_REAL.csv.

Instead it creates a clearly labeled SYNTHETIC placeholder medicine catalog
so the rest of the pipeline (demand, inventory, batches, ML) has consistent
medicine_id / medicine_name / category / manufacturer / dosage_form values
to operate on. This catalog does NOT represent any real pharmacy, hospital,
or manufacturer.

ACTION REQUIRED FROM PROJECT OWNER:
When the real files are available, place them at:
    medicine_data/real/medicine_master_REAL.csv
    medicine_data/real/medicine_transactions_REAL.csv   (if applicable)
and re-run generate_medicine_demand.py using the real catalog's medicine_id
values (and real transactions as the demand source, if the source actually
represents requests/dispensing/usage -- document what it measures before
treating it as demand).

Output: medicine_data/synthetic/medicine_master_SYNTHETIC_placeholder.csv
"""

import pandas as pd

# Illustrative catalog only -- NOT sourced from any real medicine database.
# Categories, manufacturers and pack sizes are representative labels used
# purely to give the synthetic demand/inventory pipeline realistic structure.
CATALOG = [
    # medicine_id, medicine_name, composition, manufacturer, dosage_form, pack_size, category
    ("MED001", "Paracetamol 500mg",      "Paracetamol",                 "Generic Pharma A", "Tablet",    "10x10", "Analgesic"),
    ("MED002", "Ibuprofen 400mg",        "Ibuprofen",                   "Generic Pharma B", "Tablet",    "10x10", "Analgesic"),
    ("MED003", "Amoxicillin 500mg",      "Amoxicillin",                 "Generic Pharma A", "Capsule",   "10x10", "Antibiotic"),
    ("MED004", "Azithromycin 250mg",     "Azithromycin",                "Generic Pharma C", "Tablet",    "6x5",   "Antibiotic"),
    ("MED005", "Metformin 500mg",        "Metformin Hydrochloride",     "Generic Pharma B", "Tablet",    "15x10", "Antidiabetic"),
    ("MED006", "Insulin Glargine",       "Insulin Glargine",            "Generic Pharma D", "Injection", "1x10ml","Antidiabetic"),
    ("MED007", "Amlodipine 5mg",         "Amlodipine Besylate",         "Generic Pharma A", "Tablet",    "10x10", "Antihypertensive"),
    ("MED008", "Losartan 50mg",          "Losartan Potassium",          "Generic Pharma C", "Tablet",    "10x10", "Antihypertensive"),
    ("MED009", "Omeprazole 20mg",        "Omeprazole",                  "Generic Pharma B", "Capsule",   "10x10", "Antacid"),
    ("MED010", "Ranitidine 150mg",       "Ranitidine",                  "Generic Pharma A", "Tablet",    "10x10", "Antacid"),
    ("MED011", "Cetirizine 10mg",        "Cetirizine Hydrochloride",    "Generic Pharma C", "Tablet",    "10x10", "Antihistamine"),
    ("MED012", "Levocetirizine 5mg",     "Levocetirizine",              "Generic Pharma D", "Tablet",    "10x10", "Antihistamine"),
    ("MED013", "Vitamin D3 60000IU",     "Cholecalciferol",             "Generic Pharma B", "Capsule",   "4x1",   "Vitamin/Supplement"),
    ("MED014", "Vitamin B-Complex",      "B-Complex + Vitamin C",       "Generic Pharma A", "Tablet",    "10x10", "Vitamin/Supplement"),
    ("MED015", "Salbutamol Inhaler",     "Salbutamol",                  "Generic Pharma D", "Inhaler",   "1x200MD","Respiratory"),
    ("MED016", "Montelukast 10mg",       "Montelukast Sodium",          "Generic Pharma C", "Tablet",    "10x10", "Respiratory"),
    ("MED017", "Atorvastatin 10mg",      "Atorvastatin Calcium",        "Generic Pharma A", "Tablet",    "10x10", "Cardiac"),
    ("MED018", "Clopidogrel 75mg",       "Clopidogrel Bisulfate",       "Generic Pharma B", "Tablet",    "10x10", "Cardiac"),
    ("MED019", "Betamethasone Cream",    "Betamethasone",               "Generic Pharma D", "Ointment",  "1x20g", "Dermatological"),
    ("MED020", "Clotrimazole Cream",     "Clotrimazole",                "Generic Pharma C", "Ointment",  "1x15g", "Dermatological"),
]

COLUMNS = [
    "medicine_id", "medicine_name", "composition", "manufacturer",
    "dosage_form", "pack_size", "category",
]

df = pd.DataFrame(CATALOG, columns=COLUMNS)
df["provenance"] = "SYNTHETIC_PLACEHOLDER"  # explicit, non-removable provenance flag

OUT_PATH = "/home/claude/medicine_data/synthetic/medicine_master_SYNTHETIC_placeholder.csv"
df.to_csv(OUT_PATH, index=False)

print(f"Generated {len(df)} SYNTHETIC PLACEHOLDER catalog entries -> {OUT_PATH}")
print(f"Categories: {sorted(df['category'].unique())}")
print("Reminder: replace with real files at medicine_data/real/ when available.")
