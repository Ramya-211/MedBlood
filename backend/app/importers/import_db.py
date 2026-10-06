"""
import_db.py

Standalone (non-pooled) MySQL connection helper for the one-time import
scripts. Reads credentials from environment variables only -- never
hard-coded. See backend/.env.example.
"""

import os
import mysql.connector


def get_import_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "medblood_app"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "medblood_db"),
        autocommit=False,
    )
