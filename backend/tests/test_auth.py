import secrets
import time
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import get_settings
from app.database.db import db_cursor
from app.schemas.auth import Role, ROLE_HOME
from tests.conftest import auth, login


# ---------- roles ----------
def test_exactly_three_roles_and_no_patient():
    assert {r.value for r in Role} == {"ADMIN", "PHARMACIST", "BLOOD_STAFF"}
    with db_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM users LIKE 'role'")
        col_type = cur.fetchone()["Type"]
    assert "PATIENT" not in col_type.upper() and col_type.count("'") == 6


# ---------- login ----------
def test_login_each_role_redirects_correctly(client, admin, pharmacist, blood_staff):
    for acct, path in [(admin, "/admin/dashboard"), (pharmacist, "/pharmacist/dashboard"), (blood_staff, "/blood/dashboard")]:
        r = client.post("/api/auth/login", json={"username": acct.username, "password": acct.password})
        assert r.status_code == 200
        body = r.json()
        assert body["redirect_path"] == path == ROLE_HOME[acct.role]
        assert body["user"]["role"] == acct.role and body["token_type"] == "bearer"
        assert "password" not in str(body).lower()
        assert body["user"]["last_login_at"] is not None


def test_invalid_credentials_use_same_generic_message(client, pharmacist):
    wrong_pw = client.post("/api/auth/login", json={"username": pharmacist.username, "password": "wrong-password"})
    no_user = client.post("/api/auth/login", json={"username": "t_auth_nobody_" + secrets.token_hex(3), "password": "whatever1"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"] == "Invalid username or password."


def test_login_input_validation_and_long_password(client, pharmacist):
    assert client.post("/api/auth/login", json={"username": "", "password": "x"}).status_code == 422
    assert client.post("/api/auth/login", json={"username": pharmacist.username}).status_code == 422
    r = client.post("/api/auth/login", json={"username": pharmacist.username, "password": "a" * 200})
    assert r.status_code == 401  # >72 bytes must fail cleanly, not 500


def test_sql_injection_attempts_are_inert(client, admin):
    for payload in ["' OR '1'='1", "admin'--", "x'; DROP TABLE users;--", '" OR ""="']:
        r = client.post("/api/auth/login", json={"username": payload, "password": payload})
        assert r.status_code == 401
    tok = login(client, admin)
    r = client.get("/api/admin/users", params={"search": "'; DROP TABLE users;--"}, headers=auth(tok))
    assert r.status_code == 200 and r.json()["total"] == 0
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        assert cur.fetchone()["n"] >= 1  # table still exists


def test_passwords_are_bcrypt_hashed_in_database(admin):
    with db_cursor() as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (admin.id,))
        h = cur.fetchone()["password_hash"]
    assert h.startswith("$2b$") and admin.password not in h


# ---------- /me, tokens ----------
def test_me_requires_valid_bearer_token(client, pharmacist):
    tok = login(client, pharmacist)
    r = client.get("/api/auth/me", headers=auth(tok))
    assert r.status_code == 200 and r.json()["username"] == pharmacist.username
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401


def test_tampered_forged_and_expired_tokens_rejected(client, pharmacist):
    s = get_settings()
    tok = login(client, pharmacist)
    head, payload, sig = tok.split(".")
    assert client.get("/api/auth/me", headers=auth(f"{head}.{payload}.{sig[:-2]}xx")).status_code == 401

    now = datetime.now(timezone.utc)
    base = {"sub": str(pharmacist.id), "username": pharmacist.username, "role": "ADMIN",
            "jti": "00000000-0000-0000-0000-000000000000", "iat": int(now.timestamp())}
    forged = jwt.encode({**base, "exp": int((now + timedelta(minutes=5)).timestamp())}, "attacker-secret-key-0123456789abcdef", algorithm="HS256")
    assert client.get("/api/admin/users", headers=auth(forged)).status_code == 401

    expired = jwt.encode({**base, "role": "PHARMACIST", "exp": int((now - timedelta(minutes=1)).timestamp())}, s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get("/api/auth/me", headers=auth(expired)).status_code == 401

    none_alg = jwt.encode({**base, "exp": int((now + timedelta(minutes=5)).timestamp())}, "", algorithm="HS256")
    assert client.get("/api/auth/me", headers=auth(none_alg)).status_code == 401


def test_logout_revokes_only_that_token(client, pharmacist):
    t1, t2 = login(client, pharmacist), login(client, pharmacist)
    assert client.get("/api/auth/me", headers=auth(t1)).status_code == 200
    assert client.post("/api/auth/logout", headers=auth(t1)).status_code == 200
    r = client.get("/api/auth/me", headers=auth(t1))
    assert r.status_code == 401
    assert client.post("/api/auth/logout", headers=auth(t1)).status_code == 401  # already revoked
    assert client.get("/api/auth/me", headers=auth(t2)).status_code == 200
    assert client.post("/api/auth/logout").status_code == 401


# ---------- authorization matrix ----------
def test_role_authorization_matrix(client, admin, pharmacist, blood_staff):
    endpoints = {"admin": "/api/admin/users", "medicine": "/api/medicine/filters", "blood": "/api/blood/filters"}
    expected = {
        admin: {"admin": 200, "medicine": 403, "blood": 403},
        pharmacist: {"admin": 403, "medicine": 200, "blood": 403},
        blood_staff: {"admin": 403, "medicine": 403, "blood": 200},
    }
    for acct, rules in expected.items():
        tok = login(client, acct)
        for name, url in endpoints.items():
            assert client.get(url, headers=auth(tok)).status_code == rules[name], (acct.role, name)
    for url in endpoints.values():
        assert client.get(url).status_code == 401


# ---------- account state ----------
def test_deactivated_user_cannot_login_or_reuse_token(client, admin, pharmacist):
    a_tok, p_tok = login(client, admin), login(client, pharmacist)
    r = client.patch(f"/api/admin/users/{pharmacist.id}", json={"is_active": False}, headers=auth(a_tok))
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/auth/me", headers=auth(p_tok)).status_code == 401
    r = client.post("/api/auth/login", json={"username": pharmacist.username, "password": pharmacist.password})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid username or password."


def test_role_change_takes_effect_immediately(client, admin, pharmacist):
    a_tok, p_tok = login(client, admin), login(client, pharmacist)
    assert client.get("/api/medicine/filters", headers=auth(p_tok)).status_code == 200
    r = client.patch(f"/api/admin/users/{pharmacist.id}", json={"role": "BLOOD_STAFF"}, headers=auth(a_tok))
    assert r.status_code == 200
    assert client.get("/api/medicine/filters", headers=auth(p_tok)).status_code == 403
    assert client.get("/api/blood/filters", headers=auth(p_tok)).status_code == 200


def test_admin_password_reset(client, admin, pharmacist):
    a_tok = login(client, admin)
    new_pw = secrets.token_urlsafe(14)
    r = client.patch(f"/api/admin/users/{pharmacist.id}", json={"new_password": new_pw}, headers=auth(a_tok))
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"username": pharmacist.username, "password": pharmacist.password}).status_code == 401
    assert client.post("/api/auth/login", json={"username": pharmacist.username, "password": new_pw}).status_code == 200


def test_admin_cannot_demote_or_deactivate_self(client, admin):
    tok = login(client, admin)
    assert client.patch(f"/api/admin/users/{admin.id}", json={"is_active": False}, headers=auth(tok)).status_code == 400
    assert client.patch(f"/api/admin/users/{admin.id}", json={"role": "PHARMACIST"}, headers=auth(tok)).status_code == 400
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 200


# ---------- user management ----------
def test_admin_creates_users_with_validation(client, admin, pharmacist):
    tok = login(client, admin)
    name = "t_auth_new_" + secrets.token_hex(3)
    good = {"username": name, "password": secrets.token_urlsafe(12), "full_name": "New Person", "role": "BLOOD_STAFF"}
    r = client.post("/api/admin/users", json=good, headers=auth(tok))
    assert r.status_code == 201 and r.json()["role"] == "BLOOD_STAFF" and "password" not in str(r.json()).lower()
    assert client.post("/api/admin/users", json=good, headers=auth(tok)).status_code == 409
    assert client.post("/api/admin/users", json={**good, "username": name + "x", "role": "PATIENT"}, headers=auth(tok)).status_code == 422
    assert client.post("/api/admin/users", json={**good, "username": name + "y", "password": "short"}, headers=auth(tok)).status_code == 422
    assert client.post("/api/admin/users", json={**good, "username": "bad name!"}, headers=auth(tok)).status_code == 422
    assert client.post("/api/admin/users", json={**good, "username": name + "z", "password": "a" * 80}, headers=auth(tok)).status_code == 422
    assert client.patch("/api/admin/users/99999999", json={"full_name": "x"}, headers=auth(tok)).status_code == 404
    assert client.post("/api/admin/users", json=good, headers=auth(login(client, pharmacist))).status_code == 403


def test_user_listing_filters_and_pagination(client, admin, pharmacist, blood_staff):
    tok = login(client, admin)
    r = client.get("/api/admin/users", params={"role": "PHARMACIST", "search": "t_auth_"}, headers=auth(tok))
    assert r.status_code == 200 and all(u["role"] == "PHARMACIST" for u in r.json()["items"])
    assert any(u["id"] == pharmacist.id for u in r.json()["items"])
    r = client.get("/api/admin/users", params={"role": "BLOOD_STAFF", "search": "t_auth_"}, headers=auth(tok))
    assert any(u["id"] == blood_staff.id for u in r.json()["items"])
    r = client.get("/api/admin/users", params={"limit": 1, "offset": 0, "search": "t_auth_"}, headers=auth(tok))
    assert len(r.json()["items"]) == 1 and r.json()["total"] >= 3
    assert client.get("/api/admin/users", params={"limit": 1000}, headers=auth(tok)).status_code == 422
    assert client.get("/api/admin/users", params={"role": "PATIENT"}, headers=auth(tok)).status_code == 422
    assert "password_hash" not in str(r.json())


# ---------- error handling ----------
def test_unexpected_errors_do_not_leak_stack_traces(client, monkeypatch):
    from app.services import auth_service

    def boom(*_a, **_k):
        raise RuntimeError("secret internal detail: db password xyz")
    monkeypatch.setattr(auth_service, "login", boom)
    r = client.post("/api/auth/login", json={"username": "abc", "password": "abcdefgh"})
    assert r.status_code == 500
    assert r.json() == {"detail": "An unexpected error occurred."}
    assert "secret internal detail" not in r.text and "Traceback" not in r.text


def test_config_refuses_weak_jwt_secret(monkeypatch):
    import pytest
    from app import config
    monkeypatch.setenv("JWT_SECRET", "change_me_to_a_long_random_string")
    with pytest.raises(RuntimeError):
        config._load()
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        config._load()


def test_health_and_cors_preflight(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    r = client.options("/api/auth/login", headers={"Origin": "http://localhost:5173",
                                                    "Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "content-type"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = client.options("/api/auth/login", headers={"Origin": "http://evil.example",
                                                    "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") is None
