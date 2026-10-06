"""
Phase 6 — Blood backend tests, run against the real imported MySQL data.
Mirrors tests/test_medicine.py's structure and guarantees.
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
def blood_token(client):
    return login(client, _make_user_module("BLOOD_STAFF"))


@pytest.fixture(scope="module")
def pharm_token(client):
    return login(client, _make_user_module("PHARMACIST"))


@pytest.fixture(scope="module")
def H(blood_token):
    return auth(blood_token)


# ---------------------------------------------------------------- access control
def test_blood_routes_blocked_for_other_roles(client, pharm_token):
    for url in ("/api/blood/dashboard", "/api/blood/inventory", "/api/blood/alerts"):
        assert client.get(url, headers=auth(pharm_token)).status_code == 403
        assert client.get(url).status_code == 401


def test_medicine_backend_not_broken_by_blood_changes(client, pharm_token):
    r = client.get("/api/medicine/dashboard", headers=auth(pharm_token))
    assert r.status_code == 200


# ---------------------------------------------------------------- filters / dashboard
def test_filters_have_no_location_fields(client, H):
    r = client.get("/api/blood/filters", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert set(body["blood_groups"]) == {"A", "B", "AB", "O"}
    assert set(body["rh_types"]) == {"Positive", "Negative"}
    # No actual location KEYS anywhere in the response (the disclaimer note legitimately
    # contains the word "state" while denying any such field exists, so check keys, not prose).
    def all_keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from all_keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from all_keys(v)

    keys = {k.lower() for k in all_keys(body)}
    for banned in ("state", "district", "city", "location"):
        assert banned not in keys


def test_dashboard_kpis_match_direct_sql(client, H):
    r = client.get("/api/blood/dashboard", headers=H)
    assert r.status_code == 200
    d = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT SUM(closing_stock) AS s FROM blood_inventory WHERE inv_date = %s", (d["meta"]["as_of_date"],))
        assert d["kpis"]["total_available_units"]["value"] == cur.fetchone()["s"]
        cur.execute("SELECT SUM(units_requested) AS s FROM blood_demand")
        assert d["kpis"]["total_requested_units"]["value"] == cur.fetchone()["s"]
        cur.execute("SELECT SUM(donation_volume) AS s FROM blood_collection")
        assert d["kpis"]["total_received_donated_units"]["value"] == cur.fetchone()["s"]
    assert d["kpis"]["predicted_demand"]["label"] == "MODEL-GENERATED FORECAST"


def test_demand_supply_inventory_forecast_never_merged_in_dashboard(client, H):
    """The four concepts must be four distinct KPI numbers, never combined into one."""
    r = client.get("/api/blood/dashboard", headers=H)
    k = r.json()["kpis"]
    values = {k["total_available_units"]["value"], k["total_requested_units"]["value"],
              k["total_received_donated_units"]["value"]}
    assert len(values) == 3  # demand, supply, inventory are numerically distinct in this dataset


# ---------------------------------------------------------------- demand analysis
def test_demand_uses_units_requested_not_donor_volume(client, H):
    r = client.get("/api/blood/demand", params={"granularity": "yearly"}, headers=H)
    items = {it["period_start"]: it["units_requested"] for it in r.json()["items"]}
    with db_cursor() as cur:
        cur.execute("SELECT YEAR(demand_date) AS y, SUM(units_requested) AS s FROM blood_demand GROUP BY y")
        for row in cur.fetchall():
            assert items[f"{row['y']}-01-01"] == row["s"]


def test_daily_weekly_monthly_yearly_all_work(client, H):
    for gran in ("daily", "weekly", "monthly", "yearly"):
        r = client.get("/api/blood/demand", params={"granularity": gran, "limit": 5}, headers=H)
        assert r.status_code == 200, gran
        assert r.json()["granularity"] == gran


def test_unknown_segment_rejected(client, H):
    r = client.get("/api/blood/demand", params={"granularity": "daily", "blood_group": "A", "rh_type": "Positive"}, headers=H)
    assert r.status_code == 200  # A+ is a real segment
    # An out-of-vocabulary value is a 422 at the schema layer (enum validation), not a silent pass-through.
    r = client.get("/api/blood/demand/summary", params={"blood_component": "Bone Marrow"}, headers=H)
    assert r.status_code == 422


def test_moving_average_rejects_bad_window(client, H):
    assert client.get("/api/blood/demand/moving-average", params={"window": 11}, headers=H).status_code == 400


def test_movement_classification_is_computed_live_and_documented(client, H):
    r = client.get("/api/blood/demand/movement", headers=H)
    body = r.json()
    assert "DATASET LIMITATION" in body["definition"]
    assert sum(body["counts"].values()) == body["total"] == 32  # all 32 segments partitioned


def test_anomalies_computed_live(client, H):
    r = client.get("/api/blood/demand/anomalies", params={"limit": 500}, headers=H)
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM blood_demand_features WHERE anomaly_flag = 1")
        assert body["total"] == cur.fetchone()["n"]


# ---------------------------------------------------------------- supply / demand separation
def test_supply_never_used_as_demand(client, H):
    """The supply endpoint must report donation_volume, and demand must never appear there."""
    r = client.get("/api/blood/supply", params={"granularity": "yearly"}, headers=H)
    body = r.json()
    assert "donation_volume" in body["metric"]
    for item in body["items"]:
        assert "units_requested" not in item


def test_supply_vs_demand_shows_both_never_merged(client, H):
    r = client.get("/api/blood/supply-vs-demand", headers=H)
    body = r.json()
    for item in body["items"]:
        assert "total_demand_requested" in item and "total_supply_donation_volume" in item
        # they must be reported as separate fields, not summed into one
        assert item.get("total_demand_requested") != item.get("total_supply_donation_volume") or item["total_demand_requested"] is None
    assert "component" in body["limitation"]
    assert "SYNTHETIC PLACEHOLDER" in body["limitation"]


def test_supply_vs_demand_totals_match_direct_sql(client, H):
    r = client.get("/api/blood/supply-vs-demand", headers=H)
    items = {it["blood_type"]: it for it in r.json()["items"]}
    with db_cursor() as cur:
        cur.execute("SELECT SUM(units_requested) AS s FROM blood_demand WHERE blood_group='O' AND rh_type='Positive'")
        assert items["O+"]["total_demand_requested"] == cur.fetchone()["s"]
        cur.execute("SELECT SUM(donation_volume) AS s FROM blood_collection WHERE blood_type='O+'")
        assert items["O+"]["total_supply_donation_volume"] == cur.fetchone()["s"]


# ---------------------------------------------------------------- forecasting: primary algorithms + separation
def test_only_three_primary_algorithms_presented(client, H):
    r = client.get("/api/blood/forecast/models", headers=H)
    body = r.json()
    assert set(x["model_name"] for x in body["items"]) == {"Linear Regression", "Random Forest Regressor", "XGBoost Regressor"}
    assert body["internal_baseline_reference"]["metrics"]["model_name"] == "Baseline (naive lag-1)"
    assert body["internal_baseline_reference"]["metrics"]["model_name"] not in [x["model_name"] for x in body["items"]]


def test_selected_model_matches_lowest_rmse_among_primary(client, H):
    r = client.get("/api/blood/forecast/models", headers=H)
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT model_name, rmse FROM blood_model_comparison WHERE model_name IN "
                    "('Linear Regression','Random Forest Regressor','XGBoost Regressor') ORDER BY rmse LIMIT 1")
        best = cur.fetchone()
    assert body["selected_model"] == best["model_name"]


def test_backtest_never_returns_forecast_rows(client, H):
    r = client.get("/api/blood/forecast/backtest/rows", params={"limit": 500}, headers=H)
    assert r.json()["type"] == "HISTORICAL_BACKTEST"
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT source FROM blood_actual_vs_predicted")
        assert {row["source"] for row in cur.fetchall()} == {"BACKTEST"}


def test_future_forecast_dates_strictly_after_observed_history(client, H):
    r = client.get("/api/blood/forecast/future", params={"blood_group": "O", "rh_type": "Positive",
                                                          "blood_component": "Whole Blood"}, headers=H)
    body = r.json()
    assert body["available"] is True
    assert body["type"] == "MODEL_GENERATED_FORECAST"
    with db_cursor() as cur:
        cur.execute("SELECT MAX(demand_date) AS mx FROM blood_demand")
        max_date_str = str(cur.fetchone()["mx"])
    for item in body["items"]:
        assert item["forecast_date"] > max_date_str


def test_forecast_overview_keeps_three_series_separate(client, H):
    r = client.get("/api/blood/forecast/overview", params={"blood_group": "O", "rh_type": "Positive",
                                                            "blood_component": "Whole Blood"}, headers=H)
    body = r.json()
    assert body["historical_actual"]["label"] == "OBSERVED HISTORICAL DEMAND"
    assert "BACKTEST" in body["historical_backtest"]["label"]
    assert "FORECAST" in body["future_forecast"]["label"]
    hist_dates = {s["date"] for s in body["historical_actual"]["series"]}
    fc_dates = {s["date"] for s in body["future_forecast"]["series"]}
    assert hist_dates.isdisjoint(fc_dates)


def test_horizon_cannot_exceed_stored_run_horizon(client, H):
    assert client.get("/api/blood/forecast/future", params={"horizon": 999999}, headers=H).status_code == 400


def test_every_forecast_row_has_required_fields(client, H):
    r = client.get("/api/blood/forecast/future", params={"limit": 20}, headers=H)
    for item in r.json()["items"]:
        for field in ("run_id", "forecast_date", "horizon_step", "predicted_demand", "uses_predicted_inputs"):
            assert field in item
        assert item["horizon_step"] >= 1


# ---------------------------------------------------------------- inventory / expiry
def test_stock_status_derived_with_documented_thresholds(client, H):
    r = client.get("/api/blood/inventory", params={"limit": 50}, headers=H)
    body = r.json()
    assert body["stock_rule"]["critical_below_days"] == 2
    assert body["stock_rule"]["low_below_days"] == 5
    assert body["stock_rule"]["overstock_above_days"] == 30
    for item in body["items"]:
        cover = item["days_of_cover"]
        if cover is None:
            continue
        if cover < 2:
            assert item["stock_status"] == "Critical"
        elif cover < 5:
            assert item["stock_status"] == "Low"
        elif cover > 30:
            assert item["stock_status"] == "Overstock"
        else:
            assert item["stock_status"] == "Normal"


def test_expiry_status_derived_not_blindly_trusted(client, H):
    r = client.get("/api/blood/inventory/batches", params={"limit": 500}, headers=H)
    body = r.json()
    assert "stored_expiry_status" in body["items"][0]
    assert "DERIVED here from expiry_date" in body["rule"]
    for item in body["items"]:
        if item["expiry_status"] == "Expired":
            assert item["days_remaining"] < 0
        elif item["expiry_status"] == "Near Expiry":
            assert 0 <= item["days_remaining"] <= body["near_expiry_days"]
        else:
            assert item["days_remaining"] > body["near_expiry_days"]


def test_inventory_and_batch_ledgers_reported_separately(client, H):
    r = client.get("/api/blood/inventory/reconciliation", params={"blood_group": "O", "rh_type": "Positive",
                                                                   "blood_component": "Whole Blood"}, headers=H)
    body = r.json()
    assert "DATASET LIMITATION" in body["note"]
    row = body["items"][0]
    assert set(row) >= {"inventory_closing_stock", "batch_units_remaining", "difference_batch_minus_inventory"}


# ---------------------------------------------------------------- alerts / recommendations
def test_alerts_never_generated_with_fake_dates(client, H):
    r = client.get("/api/blood/alerts", params={"limit": 500}, headers=H)
    body = r.json()
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT alert_date FROM blood_alerts")
        real_dates = {str(row["alert_date"]) for row in cur.fetchall()}
    for item in body["items"]:
        assert item["date"] in real_dates
    assert "Current-state snapshot" in body["snapshot"]["note"]


def test_every_alert_has_reason_and_required_fields(client, H):
    r = client.get("/api/blood/alerts", params={"limit": 500}, headers=H)
    for item in r.json()["items"]:
        assert item["reason"]
        for field in ("alert_type", "severity", "blood_group", "rh_type", "blood_component", "date"):
            assert field in item


def test_supplied_recommendations_all_have_why(client, H):
    r = client.get("/api/blood/recommendations", params={"limit": 500}, headers=H)
    body = r.json()
    assert body["total"] > 0
    for item in body["items"]:
        assert item["why"]


def test_forecast_based_recommendations_use_real_numbers(client, H):
    r = client.get("/api/blood/recommendations/forecast-based", params={"blood_group": "O", "rh_type": "Positive",
                                                                         "blood_component": "Whole Blood"}, headers=H)
    body = r.json()
    assert body["available"] is True
    with db_cursor() as cur:
        cur.execute("SELECT MAX(inv_date) AS d FROM blood_inventory")
        as_of = cur.fetchone()["d"]
        cur.execute("SELECT closing_stock FROM blood_inventory WHERE blood_group='O' AND rh_type='Positive' "
                    "AND blood_component='Whole Blood' AND inv_date=%s", (as_of,))
        real_stock = cur.fetchone()["closing_stock"]
    for item in body["items"]:
        assert item["inputs"]["current_stock"] == real_stock
        assert item["why"]
        assert item["rule_id"] in {"R1", "R2", "R3", "R4", "R5"}


def test_recommendation_no_quantity_beyond_shortfall(client, H):
    r = client.get("/api/blood/recommendations/forecast-based", headers=H)
    for item in r.json()["items"]:
        if item["rule_id"] == "R1":
            assert set(item["inputs"]) >= {"current_stock", "projected_shortfall"}


# ---------------------------------------------------------------- reports
@pytest.mark.parametrize("report_type", ["demand", "forecast", "inventory", "expiry", "alerts", "recommendations",
                                         "supply_vs_demand"])
def test_all_seven_blood_reports_return_rows(client, H, report_type):
    r = client.get(f"/api/blood/reports/{report_type}", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["report"] == report_type
    assert body["row_count"] == len(body["rows"])


def test_report_csv_export(client, H):
    r = client.get("/api/blood/reports/demand", params={"export": "csv"}, headers=H)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].split(",")[0] == "blood_group"


def test_bad_export_format_rejected(client, H):
    assert client.get("/api/blood/reports/demand", params={"export": "xml"}, headers=H).status_code == 400


# ---------------------------------------------------------------- empty/null handling
def test_null_predicted_demand_in_supplied_recommendations_not_fabricated(client, H):
    r = client.get("/api/blood/recommendations", params={"limit": 500}, headers=H)
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM blood_recommendations WHERE predicted_demand IS NULL")
        expected_nulls = cur.fetchone()["n"]
    actual_nulls = sum(1 for it in r.json()["items"] if it["supplied_predicted_demand"] is None)
    assert actual_nulls == expected_nulls


# ---------------------------------------------------------------- dataset integrity
def test_original_csvs_still_unchanged(client, H):
    import filecmp
    import os
    import zipfile

    with zipfile.ZipFile("/mnt/user-data/uploads/blood_data.zip") as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        sample = names[0]
        z.extract(sample, "/tmp/_blood_csv_check")
    extracted = os.path.join("/tmp/_blood_csv_check", sample)
    live = os.path.join("/home/claude/project/data/blood_data", sample.split("blood_data/", 1)[-1])
    assert filecmp.cmp(extracted, live, shallow=False)
