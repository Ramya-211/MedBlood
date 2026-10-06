"""
security.py

Password hashing (bcrypt) and JWT creation/verification (python-jose).
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import get_settings

MAX_PASSWORD_BYTES = 72  # bcrypt limit
# Valid hash used to keep login timing similar when the username does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt(rounds=12))


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError("Password exceeds 72 bytes.")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        bcrypt.checkpw(b"x", _DUMMY_HASH)
        return False
    target = password_hash.encode("utf-8") if password_hash else _DUMMY_HASH
    ok = bcrypt.checkpw(raw, target)
    return ok and password_hash is not None


def create_access_token(user_id: int, username: str, role: str):
    """Return (token, jti, expires_at_utc_naive)."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.jwt_expire_minutes)
    jti = str(uuid.uuid4())
    payload = {"sub": str(user_id), "username": username, "role": role,
               "jti": jti, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, jti, exp.replace(tzinfo=None)


def decode_access_token(token: str) -> dict | None:
    """Return payload if the signature and expiry are valid, else None."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError:
        return None
    if not all(k in payload for k in ("sub", "role", "jti", "exp")):
        return None
    return payload
