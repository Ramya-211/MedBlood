"""
admin_queries.py

Raw SQL for the Admin dashboard: system-wide counts only (no medicine/blood business logic
duplicated here -- Pharmacist/Blood Staff still own their detailed analytics, this is a
deliberately light cross-system overview, matching the "Admin dashboard must stay simple,
not duplicate every Medicine/Blood metric" project rule).
"""


def user_counts(cur):
    cur.execute("SELECT role, COUNT(*) AS n, SUM(is_active) AS active_n FROM users GROUP BY role")
    return cur.fetchall()


def medicine_overview(cur):
    cur.execute("SELECT COUNT(*) AS total_medicines FROM medicines")
    total = cur.fetchone()["total_medicines"]
    cur.execute("SELECT MAX(inv_date) AS d FROM medicine_inventory")
    as_of = cur.fetchone()["d"]
    cur.execute("SELECT COALESCE(SUM(closing_stock),0) AS units, "
                "SUM(stock_status IN ('Low','Critical')) AS low_or_critical "
                "FROM medicine_inventory WHERE inv_date = %s", (as_of,))
    inv = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS n FROM medicine_alerts")
    alerts = cur.fetchone()["n"]
    return {"total_medicines": total, "as_of_date": as_of, "total_units": int(inv["units"]),
            "low_or_critical_medicines": int(inv["low_or_critical"] or 0), "active_alerts": alerts}


def blood_overview(cur):
    cur.execute("SELECT MAX(inv_date) AS d FROM blood_inventory")
    as_of = cur.fetchone()["d"]
    cur.execute("SELECT COALESCE(SUM(closing_stock),0) AS units FROM blood_inventory WHERE inv_date = %s", (as_of,))
    units = cur.fetchone()["units"]
    cur.execute("SELECT COUNT(*) AS n FROM blood_alerts")
    alerts = cur.fetchone()["n"]
    return {"as_of_date": as_of, "total_units": int(units), "active_alerts": alerts}


def recent_alerts(cur, limit=8):
    cur.execute(
        "(SELECT 'medicine' AS domain, alert_date AS date, alert_type, severity, message FROM medicine_alerts) "
        "UNION ALL "
        "(SELECT 'blood' AS domain, alert_date AS date, alert_type, severity, message FROM blood_alerts) "
        "ORDER BY FIELD(severity,'Critical','Warning','Info'), date DESC LIMIT %s", (limit,))
    return cur.fetchall()
