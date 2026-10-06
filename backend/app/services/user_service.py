"""user_service.py — admin-side user management (create / list / update / deactivate)."""

from mysql.connector import errors as mysql_errors

from app.database.db import db_cursor
from app.database.queries import user_queries as uq
from app.services.auth_service import _public
from app.utils.security import hash_password


class UserServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def list_users(role=None, search=None, is_active=None, limit=25, offset=0):
    with db_cursor() as cur:
        rows = uq.list_users(cur, role, search, is_active, limit, offset)
        total = uq.count_users(cur, role, search, is_active)
    return {"total": total, "limit": limit, "offset": offset,
            "items": [dict(r, is_active=bool(r["is_active"])) for r in rows]}


def create_user(username, password, full_name, role) -> dict:
    try:
        with db_cursor(commit=True) as cur:
            uid = uq.insert_user(cur, username, hash_password(password), full_name, role)
            return _public(uq.get_user_by_id(cur, uid))
    except mysql_errors.IntegrityError:
        raise UserServiceError("That username is already taken.", 409)


def update_user(
    target_id,
    acting_user_id,
    username=None,
    full_name=None,
    role=None,
    is_active=None,
    new_password=None,
) -> dict:
    with db_cursor(commit=True) as cur:
        target = uq.get_user_by_id(cur, target_id)
        if not target:
            raise UserServiceError("User not found.", 404)

        removing_admin = target["role"] == "ADMIN" and target["is_active"] and (
            (role is not None and role != "ADMIN") or is_active is False)
        if removing_admin:
            if target_id == acting_user_id:
                raise UserServiceError("You cannot demote or deactivate your own admin account.", 400)
            if uq.count_active_admins(cur) <= 1:
                raise UserServiceError("At least one active admin must remain.", 400)

        pw_hash = hash_password(new_password) if new_password is not None else None
        uq.update_user_fields(cur, target_id, username, full_name, role, is_active, pw_hash)
        return _public(uq.get_user_by_id(cur, target_id))
