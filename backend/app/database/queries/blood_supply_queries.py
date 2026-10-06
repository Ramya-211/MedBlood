"""
blood_supply_queries.py

SUPPLY / COLLECTION analysis (table: blood_collection) and the Supply-vs-Demand comparison.

DATASET LIMITATION (see BLOOD_DATA_REPORT.md / Phase 1-3 disclosures): blood_collection is a
SYNTHETIC PLACEHOLDER -- no real donation dataset was ever supplied. It is also keyed only by
combined blood_type (e.g. "A+", not split into blood_group/rh_type) and has NO blood_component
breakdown at all (donations are not recorded per-component). Supply-vs-demand comparison is
therefore only possible at the blood_group + rh_type level (demand is summed across components),
never at component granularity, and this is stated in every response rather than silently merged.
"""

BUCKETS = {
    "daily": "c.collection_date",
    "weekly": "DATE_SUB(c.collection_date, INTERVAL WEEKDAY(c.collection_date) DAY)",
    "monthly": "DATE_SUB(c.collection_date, INTERVAL DAYOFMONTH(c.collection_date) - 1 DAY)",
    "yearly": "MAKEDATE(YEAR(c.collection_date), 1)",
}


def _where(blood_type, date_from, date_to):
    clauses, params = [], []
    if blood_type:
        clauses.append("c.blood_type = %s"); params.append(blood_type)
    if date_from:
        clauses.append("c.collection_date >= %s"); params.append(date_from)
    if date_to:
        clauses.append("c.collection_date <= %s"); params.append(date_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def blood_types(cur):
    cur.execute("SELECT DISTINCT blood_type FROM blood_collection ORDER BY blood_type")
    return [r["blood_type"] for r in cur.fetchall()]


def supply_date_bounds(cur):
    cur.execute("SELECT MIN(collection_date) AS min_date, MAX(collection_date) AS max_date, "
                "COUNT(DISTINCT data_type) AS n_data_types FROM blood_collection")
    return cur.fetchone()


def data_type_values(cur):
    cur.execute("SELECT DISTINCT data_type FROM blood_collection")
    return [r["data_type"] for r in cur.fetchall()]


def supply_series(cur, granularity, blood_type, date_from, date_to, by_type, limit, offset):
    bucket = BUCKETS[granularity]
    where, params = _where(blood_type, date_from, date_to)
    extra, group, order = (", c.blood_type", "period_start, c.blood_type", "period_start, c.blood_type") if by_type \
        else ("", "period_start", "period_start")
    inner_group = group
    cur.execute(f"SELECT COUNT(*) AS n FROM (SELECT {bucket} AS period_start FROM blood_collection c{where} "
                f"GROUP BY {inner_group}) t", tuple(params))
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT {bucket} AS period_start{extra}, SUM(c.donation_volume) AS donation_volume, "
        f"COUNT(DISTINCT c.collection_date) AS days_covered FROM blood_collection c{where} "
        f"GROUP BY {group} ORDER BY {order} LIMIT %s OFFSET %s", (*params, limit, offset))
    return cur.fetchall(), total


def supply_summary(cur, blood_type, date_from, date_to):
    where, params = _where(blood_type, date_from, date_to)
    cur.execute(f"SELECT COALESCE(SUM(c.donation_volume),0) AS total_donation_volume, "
                f"COUNT(DISTINCT c.collection_date) AS days, COUNT(DISTINCT c.blood_type) AS blood_types, "
                f"MIN(c.collection_date) AS first_date, MAX(c.collection_date) AS last_date "
                f"FROM blood_collection c{where}", tuple(params))
    return cur.fetchone()


def supply_by_type(cur, date_from, date_to):
    where, params = _where(None, date_from, date_to)
    cur.execute(f"SELECT c.blood_type, SUM(c.donation_volume) AS total_donation_volume, "
                f"AVG(c.donation_volume) AS avg_daily_donation_volume FROM blood_collection c{where} "
                f"GROUP BY c.blood_type ORDER BY total_donation_volume DESC", tuple(params))
    return cur.fetchall()


# ---------------------------------------------------------------- supply vs demand (blood_group+rh_type granularity)
def demand_vs_supply(cur, date_from, date_to):
    d_clauses, d_params = [], []
    if date_from:
        d_clauses.append("demand_date >= %s"); d_params.append(date_from)
    if date_to:
        d_clauses.append("demand_date <= %s"); d_params.append(date_to)
    d_where = (" WHERE " + " AND ".join(d_clauses)) if d_clauses else ""

    c_clauses, c_params = [], []
    if date_from:
        c_clauses.append("collection_date >= %s"); c_params.append(date_from)
    if date_to:
        c_clauses.append("collection_date <= %s"); c_params.append(date_to)
    c_where = (" WHERE " + " AND ".join(c_clauses)) if c_clauses else ""

    cur.execute(
        "SELECT d.blood_group, d.rh_type, CONCAT(d.blood_group, IF(d.rh_type='Positive','+','-')) AS blood_type, "
        "SUM(d.units_requested) AS total_demand_requested, SUM(d.units_issued) AS total_demand_issued "
        f"FROM blood_demand d{d_where} GROUP BY d.blood_group, d.rh_type", tuple(d_params))
    demand_rows = {r["blood_type"]: r for r in cur.fetchall()}

    cur.execute(f"SELECT blood_type, SUM(donation_volume) AS total_supply_donation_volume "
                f"FROM blood_collection{c_where} GROUP BY blood_type", tuple(c_params))
    supply_rows = {r["blood_type"]: r for r in cur.fetchall()}

    all_types = sorted(set(demand_rows) | set(supply_rows))
    out = []
    for bt in all_types:
        d = demand_rows.get(bt)
        s = supply_rows.get(bt)
        out.append({
            "blood_type": bt, "blood_group": d["blood_group"] if d else bt.rstrip("+-"),
            "rh_type": d["rh_type"] if d else ("Positive" if bt.endswith("+") else "Negative"),
            "total_demand_requested": int(d["total_demand_requested"]) if d else None,
            "total_demand_issued": int(d["total_demand_issued"]) if d else None,
            "total_supply_donation_volume": int(s["total_supply_donation_volume"]) if s else None,
        })
    return out
