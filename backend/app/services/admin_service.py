"""admin_service.py — system-wide overview for the Admin dashboard (counts only)."""

from app.database.db import db_cursor
from app.database.queries import admin_queries as aq


def dashboard_overview():
    with db_cursor() as cur:
        users = aq.user_counts(cur)
        medicine = aq.medicine_overview(cur)
        blood = aq.blood_overview(cur)
        alerts = aq.recent_alerts(cur)
    by_role = {r["role"]: {"total": r["n"], "active": int(r["active_n"])} for r in users}
    return {
        "users": {"total": sum(r["total"] for r in by_role.values()), "by_role": by_role},
        "medicine": medicine, "blood": blood,
        "active_alerts_total": medicine["active_alerts"] + blood["active_alerts"],
        "recent_alerts": alerts,
    }
