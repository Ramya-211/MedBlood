# Database Setup (MySQL 8.0+)

This project uses **MySQL 8.0 or newer**, accessed with **mysql-connector-python** and **raw parameterized SQL**.
There is no SQLAlchemy and no ORM. **MariaDB is not supported** (`init_db.py` refuses to run against it).

## 1. Prerequisites

- MySQL Server 8.0+ running and reachable
- Python 3.10+
- A MySQL admin account (e.g. `root`) — used only once, by `init_db.py`

## 2. Configure environment

```bash
cd backend
cp .env.example .env
# edit .env: set DB_PASSWORD, DB_ADMIN_PASSWORD, JWT_SECRET to real values
pip install -r requirements.txt
```

No credentials are hard-coded anywhere. `.env` must never be committed.

## 3. Initialize the database

```bash
python init_db.py
```

This will:
1. Connect as `DB_ADMIN_USER`
2. Create database `DB_NAME` (utf8mb4)
3. Create the least-privilege application user `DB_USER` (password bound as a query parameter) with privileges on that database only
4. Apply `schema.sql` (25 tables, indexes on dates, medicine IDs, blood group/Rh/component, batch IDs, alert type/severity, expiry date/status)

## 4. Import the supplied datasets

```bash
python run_import.py
```

- Reads the unmodified CSVs in `data/medicine_data/` and `data/blood_data/` (read-only).
- Truncates dataset tables first, so it is safe to re-run (`users` and `import_log` are preserved).
- Validates required fields, numeric ranges, the inventory equation, date order and duplicates. Rejected rows are counted and logged to the `import_log` table, never silently dropped.
- Structurally expected NULLs (lag/rolling warm-up rows in the feature tables) and the 11 blood recommendations with no available prediction are stored as `NULL`. Nothing is fabricated.
- Blood recommendations arrive as free text; they are split into type/severity/reason via an explicit exhaustive map. An unmapped string aborts the import rather than being guessed.

Dataset locations can be overridden with `MEDICINE_DATA_DIR` / `BLOOD_DATA_DIR`.

## 5. Verified behaviour

Tested against **MySQL 8.0.46**: schema applies cleanly, all 18 dataset tables match their source CSV row counts exactly, and repeated imports are idempotent.

## 6. Synthetic-data disclosure

All datasets loaded here are **SYNTHETIC** (created for this academic project). They are not real hospital, pharmacy or patient records. Every medicine row carries a `provenance` value, and `blood_collection.data_type` is `SYNTHETIC_PLACEHOLDER`.
