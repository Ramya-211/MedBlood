"""
db.py

MySQL access via mysql-connector-python only (connection pool, raw SQL).
Repository modules in database/queries/ receive a cursor from `db_cursor()`;
route handlers never touch SQL or connections directly.
"""

from contextlib import contextmanager

from mysql.connector import pooling

from app.config import get_settings

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = pooling.MySQLConnectionPool(
            pool_name="medblood_pool",
            pool_size=10,
            host=s.db_host,
            port=s.db_port,
            user=s.db_user,
            password=s.db_password,
            database=s.db_name,
            autocommit=False,
        )
    return _pool


@contextmanager
def db_cursor(commit: bool = False):
    """Yield a dict cursor from a pooled connection.
    Commits if commit=True and no error occurred; always rolls back on error and closes."""
    conn = _get_pool().get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
