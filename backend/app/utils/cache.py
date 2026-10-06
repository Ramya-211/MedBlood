"""Tiny thread-safe TTL cache for rarely-changing lookups (as-of date, filter lists, model metrics).
Avoids repeated identical queries per request without ever caching user-specific or filtered data."""

import threading
import time

_lock = threading.Lock()
_store: dict = {}


def cached(key: str, ttl_seconds: int, loader):
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and now - hit[0] < ttl_seconds:
            return hit[1]
    value = loader()
    with _lock:
        _store[key] = (now, value)
    return value


def clear_cache():
    with _lock:
        _store.clear()
