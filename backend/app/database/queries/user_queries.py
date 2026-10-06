"""
user_queries.py

Raw, parameterized SQL for users and revoked tokens (repository layer).
Only fixed SQL fragments are ever concatenated; every value is a bound parameter.
"""
from mysql.connector import errors as mysql_errors
USER_COLUMNS = "id, username, password_hash, full_name, role, is_active, created_at, last_login_at"
PUBLIC_COLUMNS = "id, username, full_name, role, is_active, created_at, last_login_at"


def get_user_by_username(cur, username):
    cur.execute(f"SELECT {USER_COLUMNS} FROM users WHERE username = %s", (username,))
    return cur.fetchone()


def get_user_by_id(cur, user_id):
    cur.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))
    return cur.fetchone()


def _filters(role, search, is_active):
    clauses, params = [], []
    if role:
        clauses.append("role = %s")
        params.append(role)
    if search:
        clauses.append("(username LIKE %s OR full_name LIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    if is_active is not None:
        clauses.append("is_active = %s")
        params.append(1 if is_active else 0)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_users(cur, role=None, search=None, is_active=None, limit=25, offset=0):
    where, params = _filters(role, search, is_active)
    cur.execute(
        f"SELECT {PUBLIC_COLUMNS} FROM users {where} ORDER BY id LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return cur.fetchall()


def count_users(cur, role=None, search=None, is_active=None):
    where, params = _filters(role, search, is_active)
    cur.execute(f"SELECT COUNT(*) AS n FROM users {where}", tuple(params))
    return cur.fetchone()["n"]


def count_active_admins(cur):
    cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'ADMIN' AND is_active = 1")
    return cur.fetchone()["n"]


def insert_user(cur, username, password_hash, full_name, role):
    cur.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
        (username, password_hash, full_name, role),
    )
    return cur.lastrowid


def update_user_fields(
    cur,
    user_id,
    username=None,
    full_name=None,
    role=None,
    is_active=None,
    password_hash=None,
):
    sets, params = [], []

    if username is not None:
        sets.append("username = %s")
        params.append(username)

    if full_name is not None:
        sets.append("full_name = %s")
        params.append(full_name)

    if role is not None:
        sets.append("role = %s")
        params.append(role)

    if is_active is not None:
        sets.append("is_active = %s")
        params.append(1 if is_active else 0)

    if password_hash is not None:
        sets.append("password_hash = %s")
        params.append(password_hash)

    if not sets:
        return 0

    try:
        cur.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE id = %s",
            (*params, user_id),
        )
    except mysql_errors.IntegrityError:
        raise

    return cur.rowcount


def set_last_login(cur, user_id):
    cur.execute("UPDATE users SET last_login_at = UTC_TIMESTAMP() WHERE id = %s", (user_id,))


def revoke_token(cur, jti, user_id, expires_at):
    cur.execute(
        "INSERT IGNORE INTO revoked_tokens (jti, user_id, expires_at) VALUES (%s, %s, %s)",
        (jti, user_id, expires_at),
    )


def is_token_revoked(cur, jti):
    cur.execute("SELECT 1 AS x FROM revoked_tokens WHERE jti = %s", (jti,))
    return cur.fetchone() is not None


def purge_expired_revoked_tokens(cur):
    cur.execute("DELETE FROM revoked_tokens WHERE expires_at < UTC_TIMESTAMP()")
    return cur.rowcount
