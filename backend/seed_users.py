"""
seed_users.py

Creates the initial Admin / Pharmacist / Blood Staff accounts.
Passwords are read from environment variables (SEED_*_PASSWORD); nothing is hard-coded.
Existing usernames are left untouched. Roles are exactly ADMIN, PHARMACIST, BLOOD_STAFF.

Usage:
    python seed_users.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.services import user_service  # noqa: E402  (also loads .env via app.config)

ACCOUNTS = [
    ("ADMIN", "SEED_ADMIN_USERNAME", "admin", "SEED_ADMIN_PASSWORD", "System Administrator"),
    ("PHARMACIST", "SEED_PHARMACIST_USERNAME", "pharmacist1", "SEED_PHARMACIST_PASSWORD", "Pharmacist"),
    ("BLOOD_STAFF", "SEED_BLOOD_STAFF_USERNAME", "bloodstaff1", "SEED_BLOOD_STAFF_PASSWORD", "Blood Staff"),
]


def main():
    for role, user_env, user_default, pw_env, full_name in ACCOUNTS:
        username = os.environ.get(user_env, user_default)
        password = os.environ.get(pw_env, "")
        if not password:
            sys.exit(f"ERROR: {pw_env} is required (min 8 characters). See .env.example.")
        try:
            user_service.create_user(username, password, full_name, role)
            print(f"Created {role} user '{username}'.")
        except user_service.UserServiceError as e:
            print(f"Skipped {role} user '{username}': {e}")


if __name__ == "__main__":
    main()
