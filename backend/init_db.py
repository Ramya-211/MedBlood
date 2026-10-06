"""
init_db.py

One-time MySQL initializer. Uses mysql-connector-python and raw SQL only.

What it does:
  1. Connects to MySQL as an ADMIN account (DB_ADMIN_USER / DB_ADMIN_PASSWORD).
  2. Creates the application database (DB_NAME) if it does not exist.
  3. Creates the least-privilege application user (DB_USER / DB_PASSWORD)
     and grants it privileges on that database only.
  4. Applies schema.sql (all tables and indexes).

All values come from environment variables (see .env.example).
Nothing is hard-coded. Target server: MySQL 8.0+.

Usage:
    python init_db.py
"""

import os
import re
import sys

import mysql.connector
from mysql.connector import Error

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # python-dotenv optional; plain environment variables also work


def require_env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"ERROR: environment variable {name} is required (see .env.example).")
    return value


def split_sql_statements(sql_text):
    """Split schema.sql into individual statements (schema has no procedures/triggers)."""
    lines = [ln for ln in sql_text.splitlines() if not ln.strip().startswith("--")]
    cleaned = "\n".join(lines)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def main():
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "3306"))
    admin_user = require_env("DB_ADMIN_USER")
    admin_password = os.environ.get("DB_ADMIN_PASSWORD", "")
    db_name = require_env("DB_NAME")
    app_user = require_env("DB_USER")
    app_password = require_env("DB_PASSWORD")

    if not re.fullmatch(r"[A-Za-z0-9_]+", db_name) or not re.fullmatch(r"[A-Za-z0-9_]+", app_user):
        sys.exit("ERROR: DB_NAME and DB_USER may only contain letters, digits and underscores.")

    try:
        conn = mysql.connector.connect(host=host, port=port, user=admin_user, password=admin_password)
    except Error as e:
        sys.exit(f"ERROR: could not connect to MySQL as admin: {e}")

    cur = conn.cursor()
    server_version = conn.server_info
    print(f"Connected to MySQL server version: {server_version}")
    if "mariadb" in server_version.lower():
        conn.close()
        sys.exit("ERROR: this project targets MySQL 8.0+. A MariaDB server was detected; please use MySQL.")

    # Identifiers (database/user names) cannot be bound as parameters; they are
    # validated against a strict allow-pattern above. Password IS bound as a parameter.
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (app_user, app_password))
    cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO %s@'%%'", (app_user,))
    cur.execute("FLUSH PRIVILEGES")
    conn.commit()
    print(f"Database `{db_name}` and application user `{app_user}` are ready.")

    cur.execute(f"USE `{db_name}`")
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        statements = split_sql_statements(f.read())

    applied = 0
    for stmt in statements:
        if stmt.upper().startswith(("CREATE DATABASE", "USE ")):
            continue  # handled above
        cur.execute(stmt)
        applied += 1
    conn.commit()
    print(f"Applied {applied} schema statements from schema.sql.")

    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables present ({len(tables)}): {', '.join(sorted(tables))}")
    conn.close()


if __name__ == "__main__":
    main()
