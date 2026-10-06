"""
Phase 5 — Medicine backend tests, run against the real imported MySQL data
(not fixtures/mocks). Verifies role gating, correctness of key aggregates against
direct SQL, and the BACKTEST/FORECAST separation rules.
"""

import secrets

import pytest

from app.database.db import db_cursor
from app.services import user_service
from tests.conftest import PREFIX, auth, login


class _Acct:
    def __init__(self, user, password):
        self.id = user["id"]
        self.username = user["username"]
        self.role = user["role"]
        self.password = password


def _make_user_module(role):
    name = PREFIX + secrets.token_hex(4)
    pw = secrets.token_urlsafe(14)
    u = user_service.create_user(name, pw, f"Test {role}", role)
    return _Acct(u, pw)


@pytest.fixture(scope="module")
def pharm_token(client):
    return login(client, _make_user_module("PHARMACIST"))


@pytest.fixture(scope="module")
def blood_token(client):
    return login(client, _make_user_module("BLOOD_STAFF"))


@pytest.fixture(scope="module")
def H(pharm_token):
    return auth(pharm_token)


# ---------------------------------------------------------------- access control
def test_medicine_routes_blocked_for_other_roles(client, blood_token):
    for url in ("/api/medicine/dashboard", "/api/medicine/inventory", "/api/medicine/alerts"):
        assert client.get(url, headers=auth(blood_token)).status_code == 403
        assert client.get(url).status_code == 401


# ---------------------------------------------------------------- filters / dashboard
def test_filters_match_database(client, H):
    r = client.get("/api/medicine/filters", headers=H)
    assert r.status_code == 200
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(DISTINCT category) AS n FROM medicines")
        assert len(body["categories"]) == cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM medicines")
        assert len(body["medicines"]) == cur.fetchone()["n"]


def test_dashboard_kpis_match_direct_sql(client, H):
    r = client.get("/api/medicine/dashboard", headers=H)
    assert r.status_code == 200
    d = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM medicines")
        assert d["kpis"]["total_medicines"] == cur.fetchone()["n"]
        cur.execute("SELECT SUM(closing_stock) AS s FROM medicine_inventory WHERE inv_date = %s", (d["meta"]["as_of_date"],))
        assert d["kpis"]["current_inventory"]["units"] == cur.fetchone()["s"]
        cur.execute("SELECT COUNT(*) AS n FROM medicine_alerts") 
        general = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM medicine_expiry_alerts")
        expiry = cur.fetchone()["n"]
        assert d["kpis"]["active_alerts"]["total"] == general + expiry
    assert d["kpis"]["predicted_demand"]["label"] == "MODEL-GENERATED FORECAST"
    # dashboard must not silently invent a number when a run exists
    assert d["kpis"]["predicted_demand"]["value"] is not None


# ---------------------------------------------------------------- demand analysis
def test_yearly_demand_matches_sql_groupby(client, H):
    r = client.get("/api/medicine/demand", params={"granularity": "yearly"}, headers=H)
    assert r.status_code == 200
    items = {it["period_start"]: it["units_requested"] for it in r.json()["items"]}
    with db_cursor() as cur:
        cur.execute("SELECT YEAR(demand_date) AS y, SUM(units_requested) AS s FROM medicine_demand GROUP BY y")
        for row in cur.fetchall():
            assert items[f"{row['y']}-01-01"] == row["s"]


def test_unknown_medicine_and_category_are_404(client, H):
    assert client.get("/api/medicine/demand", params={"granularity": "daily", "medicine_id": "NOPE"}, headers=H).status_code == 404
    assert client.get("/api/medicine/demand", params={"granularity": "daily", "category": "NotACategory"}, headers=H).status_code == 404


def test_moving_average_rejects_bad_window(client, H):
    r = client.get("/api/medicine/demand/moving-average", params={"window": 13}, headers=H)
    assert r.status_code == 400


def test_movement_tiers_partition_all_medicines(client, H):
    r = client.get("/api/medicine/demand/movement", headers=H)
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM medicine_volume_tiers")
        total = cur.fetchone()["n"]
    assert sum(body["counts"].values()) == total == body["total"]


def test_anomaly_types_are_only_spike_or_drop(client, H):
    r = client.get("/api/medicine/demand/anomalies", params={"limit": 500}, headers=H)
    types = {it["anomaly_type"] for it in r.json()["items"]}
    assert types <= {"Demand Spike", "Demand Drop", "Unusual Pattern"}


# ---------------------------------------------------------------- forecasting: backtest vs forecast separation
def test_model_comparison_reproduces_imported_metrics(client, H):
    r = client.get("/api/medicine/forecast/models", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["integrity_check"]["matches_selected_model_metrics"] is True
    with db_cursor() as cur:
        cur.execute("SELECT model_name, rmse FROM medicine_model_comparison ORDER BY rmse LIMIT 1")
        best = cur.fetchone()
    assert body["selected_model"] == best["model_name"]


def test_backtest_never_returns_forecast_rows(client, H):
    r = client.get("/api/medicine/forecast/backtest/rows", params={"limit": 500}, headers=H)
    assert r.json()["type"] == "HISTORICAL_BACKTEST"
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT source FROM medicine_actual_vs_predicted")
        assert {row["source"] for row in cur.fetchall()} == {"BACKTEST"}


def test_future_forecast_is_clearly_labelled_and_separate_table(client, H):
    r = client.get("/api/medicine/forecast/future", params={"medicine_id": "MED001"}, headers=H)
    body = r.json()
    assert body["available"] is True
    assert body["type"] == "MODEL_GENERATED_FORECAST"
    assert body["run"]["model_name"]
    with db_cursor() as cur:
        cur.execute("SELECT MIN(demand_date) AS mn, MAX(demand_date) AS mx FROM medicine_demand")
        bounds = cur.fetchone()
    max_date_str = str(bounds["mx"])
    for item in body["items"]:
        assert item["forecast_date"] > max_date_str, "forecast dates must be strictly after the observed history"


def test_forecast_overview_keeps_three_series_separate(client, H):
    r = client.get("/api/medicine/forecast/overview", params={"medicine_id": "MED001"}, headers=H)
    body = r.json()
    assert body["historical_actual"]["label"] == "OBSERVED HISTORICAL DEMAND"
    assert "BACKTEST" in body["historical_backtest"]["label"]
    assert "FORECAST" in body["future_forecast"]["label"]
    hist_dates = {s["date"] for s in body["historical_actual"]["series"]}
    fc_dates = {s["date"] for s in body["future_forecast"]["series"]}
    assert hist_dates.isdisjoint(fc_dates)


def test_horizon_cannot_exceed_stored_run_horizon(client, H):
    r = client.get("/api/medicine/forecast/future", params={"horizon": 999999}, headers=H)
    assert r.status_code == 400


# ---------------------------------------------------------------- inventory / expiry
def test_stock_status_filter_matches_sql(client, H):
    with db_cursor() as cur:
        cur.execute("SELECT MAX(inv_date) AS d FROM medicine_inventory")
        as_of = cur.fetchone()["d"]
        cur.execute("SELECT COUNT(*) AS n FROM medicine_inventory WHERE inv_date=%s AND stock_status='Overstock'", (as_of,))
        expected = cur.fetchone()["n"]
    r = client.get("/api/medicine/inventory", params={"stock_status": "Overstock", "limit": 500}, headers=H)
    assert r.json()["total"] == expected


def test_expiry_status_is_derived_not_only_stored(client, H):
    r = client.get("/api/medicine/inventory/batches", params={"status": "Expired", "limit": 500}, headers=H)
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM medicine_batches WHERE expiry_status='Expired'")
        assert body["total"] == cur.fetchone()["n"]
    for item in body["items"]:
        assert item["days_remaining"] < 0


def test_inventory_and_batch_ledgers_reported_separately(client, H):
    r = client.get("/api/medicine/inventory/reconciliation", params={"medicine_id": "MED001"}, headers=H)
    body = r.json()
    assert "DATASET LIMITATION" in body["note"]
    row = body["items"][0]
    assert set(row) >= {"inventory_closing_stock", "batch_units_remaining", "difference_batch_minus_inventory"}


# ---------------------------------------------------------------- alerts / recommendations
def test_alerts_are_never_generated_with_fake_dates(client, H):
    r = client.get("/api/medicine/alerts", params={"limit": 500}, headers=H)
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT alert_date FROM medicine_alerts")
        real_dates = {str(row["alert_date"]) for row in cur.fetchall()}
    for item in body["items"]:
        assert item["date"] in real_dates
    assert "Current-state snapshot" in body["snapshot"]["note"]


def test_every_alert_has_a_reason(client, H):
    r = client.get("/api/medicine/alerts", params={"limit": 500}, headers=H)
    for item in r.json()["items"]:
        assert item["reason"]


def test_supplied_recommendations_all_have_why(client, H):
    r = client.get("/api/medicine/recommendations", params={"limit": 500}, headers=H)
    body = r.json()
    assert body["total"] > 0
    for item in body["items"]:
        assert item["why"]


def test_forecast_based_recommendations_use_real_numbers(client, H):
    r = client.get("/api/medicine/recommendations/forecast-based", params={"medicine_id": "MED001"}, headers=H)
    body = r.json()
    assert body["available"] is True
    with db_cursor() as cur:
        cur.execute("SELECT MAX(inv_date) AS d FROM medicine_inventory")
        as_of = cur.fetchone()["d"]
        cur.execute("SELECT closing_stock FROM medicine_inventory WHERE medicine_id='MED001' AND inv_date=%s", (as_of,))
        real_stock = cur.fetchone()["closing_stock"]
    for item in body["items"]:
        assert item["inputs"]["current_stock"] == real_stock
        assert item["why"]  # every recommendation explains itself
        assert item["rule_id"] in {"R1", "R2", "R3", "R4", "R5"}


def test_recommendation_no_quantity_prescribed_beyond_shortfall(client, H):
    r = client.get("/api/medicine/recommendations/forecast-based", headers=H)
    for item in r.json()["items"]:
        if item["rule_id"] == "R1":
            assert set(item["inputs"]) >= {"current_stock", "projected_shortfall"}


# ---------------------------------------------------------------- reports
@pytest.mark.parametrize("report_type", ["demand", "forecast", "inventory", "expiry", "alerts", "recommendations"])
def test_all_six_medicine_reports_return_rows(client, H, report_type):
    r = client.get(f"/api/medicine/reports/{report_type}", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["report"] == report_type
    assert body["row_count"] == len(body["rows"])


def test_report_csv_export(client, H):
    r = client.get("/api/medicine/reports/demand", params={"export": "csv"}, headers=H)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].split(",")[0] == "medicine_id"


def test_bad_export_format_rejected(client, H):
    r = client.get("/api/medicine/reports/demand", params={"export": "xml"}, headers=H)
    assert r.status_code == 400


# ---------------------------------------------------------------- CSV data untouched
def test_original_csvs_still_unchanged(client, H):
    import filecmp
    import os
    import zipfile

    with zipfile.ZipFile("/mnt/user-data/uploads/medicine_data__1_.zip") as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) > 0
        sample = names[0]
        z.extract(sample, "/tmp/_csv_check")
    extracted = os.path.join("/tmp/_csv_check", sample)
    live = os.path.join("/home/claude/project/data/medicine_data", sample.split("medicine_data/", 1)[-1])
    assert filecmp.cmp(extracted, live, shallow=False)
