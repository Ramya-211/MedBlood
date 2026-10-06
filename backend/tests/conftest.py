import os
import secrets
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Tests need a JWT secret; generate a throwaway one if the environment doesn't provide it.
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))

from fastapi.testclient import TestClient  # noqa: E402

from app.database.db import db_cursor  # noqa: E402
from app.main import app  # noqa: E402
from app.services import user_service  # noqa: E402

PREFIX = "t_auth_"


@pytest.fixture(scope="session")
def client():
    return TestClient(app, raise_server_exceptions=False)


def _cleanup():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM chat_conversations WHERE user_id IN (SELECT id FROM users WHERE username LIKE %s)", (PREFIX + "%",))
        cur.execute("DELETE FROM revoked_tokens WHERE user_id IN (SELECT id FROM users WHERE username LIKE %s)", (PREFIX + "%",))
        cur.execute("DELETE FROM users WHERE username LIKE %s", (PREFIX + "%",))


@pytest.fixture(scope="session", autouse=True)
def _session_cleanup():
    _cleanup()
    yield
    _cleanup()


class Account:
    def __init__(self, user, password):
        self.id = user["id"]
        self.username = user["username"]
        self.role = user["role"]
        self.password = password


@pytest.fixture
def make_user():
    """Factory: creates a user with a random password (no hard-coded credentials)."""
    def _make(role):
        name = PREFIX + secrets.token_hex(4)
        pw = secrets.token_urlsafe(14)
        u = user_service.create_user(name, pw, f"Test {role}", role)
        return Account(u, pw)
    return _make


def login(client, acct):
    r = client.post("/api/auth/login", json={"username": acct.username, "password": acct.password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(make_user):
    return make_user("ADMIN")


@pytest.fixture
def pharmacist(make_user):
    return make_user("PHARMACIST")


@pytest.fixture
def blood_staff(make_user):
    return make_user("BLOOD_STAFF")
