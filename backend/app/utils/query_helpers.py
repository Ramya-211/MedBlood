"""Shared helpers for query-building in services/repositories.
Nothing here ever places user input into SQL text: sort keys are resolved through allow-lists,
and every value travels as a bound parameter."""

import csv
import io
from datetime import date, datetime, timedelta

from app.utils.errors import BadRequestError

MAX_EXPORT_ROWS = 100_000


def parse_date(value, name):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        raise BadRequestError(f"{name} must be a valid date in YYYY-MM-DD format.")


def validate_range(date_from, date_to):
    d_from, d_to = parse_date(date_from, "date_from"), parse_date(date_to, "date_to")
    if d_from and d_to and d_from > d_to:
        raise BadRequestError("date_from must not be after date_to.")
    return d_from, d_to


def resolve_sort(sort_key, order, allowed: dict, default_key):
    """allowed maps public sort keys -> SQL column expressions (fixed strings owned by the repository)."""
    key = sort_key if sort_key in allowed else default_key
    if sort_key and sort_key not in allowed:
        raise BadRequestError(f"Unsupported sort key '{sort_key}'. Allowed: {', '.join(sorted(allowed))}.")
    direction = "DESC" if str(order).lower() == "desc" else "ASC"
    return f"{allowed[key]} {direction}"


def page(items, total, limit, offset, **extra):
    return {"total": total, "limit": limit, "offset": offset, "items": items, **extra}


def period_days(period_start: date, granularity: str) -> int:
    """Number of calendar days a full period would contain (used to flag partial periods)."""
    if granularity == "daily":
        return 1
    if granularity == "weekly":
        return 7
    if granularity == "monthly":
        nxt = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return (nxt - period_start).days
    if granularity == "yearly":
        return 366 if (period_start.year % 4 == 0 and (period_start.year % 100 != 0 or period_start.year % 400 == 0)) else 365
    raise ValueError(granularity)


def rows_to_csv(rows: list, columns: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r.get(c) for c in columns])
    return buf.getvalue()


def jsonable(obj):
    """Make DB rows JSON-safe (Decimal -> float, date -> ISO string)."""
    from decimal import Decimal
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj
