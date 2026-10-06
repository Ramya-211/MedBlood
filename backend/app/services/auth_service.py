"""
auth_service.py

Authentication business logic: credential check, token issue, logout
(server-side revocation) and token -> user resolution.
"""

from app.database.db import db_cursor
from app.database.queries import user_queries as uq
from app.schemas.auth import ROLE_HOME
from app.utils.security import (verify_password, create_access_token, decode_access_token)
from app.config import get_settings


class AuthError(Exception):
    """Raised for any authentication failure. Message is safe to show to users."""


def _public(u: dict) -> dict:
    return {k: u[k] for k in ("id", "username", "full_name", "role", "is_active", "created_at", "last_login_at")} | {
        "is_active": bool(u["is_active"])}


def login(username: str, password: str) -> dict:
    with db_cursor(commit=True) as cur:
        user = uq.get_user_by_username(cur, username)
        password_ok = verify_password(password, user["password_hash"] if user else None)
        # Same generic message for unknown user, wrong password and inactive account.
        if not user or not password_ok or not user["is_active"]:
            raise AuthError("Invalid username or password.")
        uq.set_last_login(cur, user["id"])
        token, _jti, _exp = create_access_token(user["id"], user["username"], user["role"])
        fresh = uq.get_user_by_id(cur, user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": get_settings().jwt_expire_minutes * 60,
        "user": _public(fresh),
        "redirect_path": ROLE_HOME[fresh["role"]],
    }


def resolve_user_from_token(token: str) -> dict:
    """Validate signature/expiry, check revocation, and re-load the user from MySQL
    (so deactivation or role changes take effect immediately)."""
    payload = decode_access_token(token)
    if payload is None:
        raise AuthError("Invalid or expired token.")
    with db_cursor() as cur:
        if uq.is_token_revoked(cur, payload["jti"]):
            raise AuthError("Session has been logged out.")
        user = uq.get_user_by_id(cur, int(payload["sub"]))
    if not user or not user["is_active"]:
        raise AuthError("Account is not available.")
    result = _public(user)
    result["jti"] = payload["jti"]
    result["token_exp"] = payload["exp"]
    return result


def logout(token: str) -> None:
    payload = decode_access_token(token)
    if payload is None:
        return  # already unusable
    from datetime import datetime, timezone
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)
    with db_cursor(commit=True) as cur:
        uq.revoke_token(cur, payload["jti"], int(payload["sub"]), expires_at)
        uq.purge_expired_revoked_tokens(cur)
