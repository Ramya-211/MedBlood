"""
tools.py

The tool layer the chatbot (LLM or deterministic fallback) calls. Every tool is a thin,
parameter-validating wrapper around an EXISTING service function from Phase 5/6 -- no business
logic or SQL is duplicated here. This is also where role authorization is enforced for real
(not just via a prompt instruction): a Pharmacist's token can never execute a blood_* tool,
and a Blood Staff token can never execute a medicine_* tool, regardless of what the LLM (or a
crafted prompt) asks for. Admin may call both.

Each tool returns a plain JSON-safe dict (via jsonable()). Tool execution never raises a raw
exception to the LLM/user; domain errors become a structured {"error": "..."} the caller can
turn into a clarification or an honest "I couldn't find that" response.
"""

from datetime import date

from app.services import medicine_service as msvc
from app.services import medicine_inventory_service as misvc
from app.services import medicine_expiry_service as mesvc
from app.services import medicine_alert_service as masvc
from app.services import medicine_recommendation_service as mrsvc
from app.services import medicine_report_service as mrepsvc
from app.services import blood_service as bsvc
from app.services import blood_inventory_service as bisvc
from app.services import blood_expiry_service as besvc
from app.services import blood_alert_service as basvc
from app.services import blood_recommendation_service as brsvc
from app.services import blood_report_service as brepsvc
from app.utils.errors import ServiceError
from app.utils.query_helpers import jsonable

MEDICINE_ROLES = {"PHARMACIST", "ADMIN"}
BLOOD_ROLES = {"BLOOD_STAFF", "ADMIN"}


class ToolAuthorizationError(Exception):
    def __init__(self, domain):
        self.domain = domain
        super().__init__(f"Not authorized for {domain} data.")


class ToolExecutionError(Exception):
    pass


def _require(user, roles, domain):
    if user["role"] not in roles:
        raise ToolAuthorizationError(domain)


def _d(v):
    return v.isoformat() if isinstance(v, date) else v


def _call(fn, *args, **kwargs):
    try:
        return jsonable(fn(*args, **kwargs))
    except ServiceError as e:
        return {"error": e.message}


# ============================================================================ MEDICINE TOOLS
def get_medicine_inventory(user, medicine_id=None, category=None, stock_status=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(misvc.inventory, stock_status, medicine_id, category, None, None, None, "asc", 50, 0)


def get_medicine_demand(user, medicine_id=None, category=None, granularity="daily", date_from=None, date_to=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.demand_series, granularity, medicine_id, category, date_from, date_to, False, 60, 0)


def get_medicine_demand_summary(user, medicine_id=None, category=None, date_from=None, date_to=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.demand_summary, medicine_id, category, date_from, date_to)


def get_medicine_trends(user, medicine_id=None, category=None, direction=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.demand_trends, direction, medicine_id, category, None, None, "asc")


def get_medicine_growth(user, medicine_id=None, category=None, period="month"):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.demand_growth, period, medicine_id, category)


def get_medicine_movement(user, tier=None, category=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.demand_movement, tier, category, None, None, "desc")


def get_medicine_forecast(user, medicine_id=None, category=None, horizon=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.future_forecast, medicine_id, category, None, horizon, 30, 0)


def get_medicine_backtest(user, medicine_id=None, category=None, date_from=None, date_to=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.backtest, medicine_id, category, date_from, date_to)


def get_medicine_model_comparison(user):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(msvc.model_comparison)


def get_medicine_expiry(user, medicine_id=None, category=None, status=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(mesvc.expiry_list, status, medicine_id, category, None, None, None, None, None, None,
                 "days_remaining", "asc", 50, 0)


def get_medicine_alerts(user, medicine_id=None, category=None, severity=None, alert_type=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(masvc.alerts, alert_type, severity, medicine_id, category, None, None, None, "severity", "asc", 50, 0)


def get_medicine_recommendations(user, medicine_id=None, category=None, recommendation_type=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(mrsvc.recommendations, recommendation_type, None, medicine_id, category, None, None, None,
                 "severity", "asc", 50, 0)


def get_medicine_forecast_recommendations(user, medicine_id=None, category=None, horizon_days=None):
    _require(user, MEDICINE_ROLES, "medicine")
    return _call(mrsvc.forecast_based, horizon_days, medicine_id, category)


def get_medicine_report(user, report_type, medicine_id=None, category=None, date_from=None, date_to=None):
    _require(user, MEDICINE_ROLES, "medicine")
    fn = mrepsvc.REPORT_FUNCS.get(report_type)
    if not fn:
        return {"error": f"Unknown medicine report type '{report_type}'."}
    if report_type == "demand":
        return _call(fn, medicine_id, category, date_from, date_to, None)
    if report_type in ("inventory",):
        return _call(fn, medicine_id, category, date_to)
    if report_type == "expiry":
        return _call(fn, medicine_id, category, date_to, None)
    if report_type == "alerts":
        return _call(fn, medicine_id, category, date_from, date_to, None, None)
    return _call(fn, medicine_id, category, date_from, date_to)


# ============================================================================ BLOOD TOOLS
def get_blood_inventory(user, blood_group=None, rh_type=None, blood_component=None, stock_status=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bisvc.inventory, stock_status, blood_group, rh_type, blood_component, None, None, "asc", 50, 0)


def get_blood_demand(user, blood_group=None, rh_type=None, blood_component=None, granularity="daily",
                     date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.demand_series, granularity, blood_group, rh_type, blood_component, date_from, date_to,
                 False, 60, 0)


def get_blood_demand_summary(user, blood_group=None, rh_type=None, blood_component=None, date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.demand_summary, blood_group, rh_type, blood_component, date_from, date_to)


def get_blood_supply(user, blood_type=None, granularity="monthly", date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.supply_series, granularity, blood_type, date_from, date_to, False, 60, 0)


def get_blood_supply_vs_demand(user, date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.supply_vs_demand, date_from, date_to)


def get_blood_trends(user, blood_group=None, rh_type=None, blood_component=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.demand_trends, blood_group, rh_type, blood_component)


def get_blood_growth(user, blood_group=None, rh_type=None, blood_component=None, period="month"):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.demand_growth, period, blood_group, rh_type, blood_component)


def get_blood_movement(user, blood_component=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.demand_movement, blood_component, None, "desc")


def get_blood_forecast(user, blood_group=None, rh_type=None, blood_component=None, horizon=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.future_forecast, blood_group, rh_type, blood_component, None, horizon, 30, 0)


def get_blood_backtest(user, blood_group=None, rh_type=None, blood_component=None, date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.backtest, blood_group, rh_type, blood_component, date_from, date_to)


def get_blood_model_comparison(user):
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.model_comparison)


def get_blood_expiry(user, blood_group=None, rh_type=None, blood_component=None, status=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(besvc.expiry_list, status, blood_group, rh_type, blood_component, None, None, None, None, None,
                 "days_remaining", "asc", 50, 0)


def get_blood_alerts(user, blood_group=None, rh_type=None, blood_component=None, severity=None, alert_type=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(basvc.alerts, alert_type, severity, blood_group, rh_type, blood_component, None, None,
                 "severity", "asc", 50, 0)


def get_blood_recommendations(user, blood_group=None, rh_type=None, blood_component=None, recommendation_type=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(brsvc.recommendations, recommendation_type, None, blood_group, rh_type, blood_component, None,
                 None, "severity", "asc", 50, 0)


def get_blood_forecast_recommendations(user, blood_group=None, rh_type=None, blood_component=None, horizon_days=None):
    _require(user, BLOOD_ROLES, "blood")
    return _call(brsvc.forecast_based, horizon_days, blood_group, rh_type, blood_component)


def get_blood_report(user, report_type, blood_group=None, rh_type=None, blood_component=None, date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    fn = brepsvc.REPORT_FUNCS.get(report_type)
    if not fn:
        return {"error": f"Unknown blood report type '{report_type}'."}
    if report_type in ("demand", "forecast", "recommendations"):
        return _call(fn, blood_group, rh_type, blood_component, date_from, date_to)
    if report_type == "inventory":
        return _call(fn, blood_group, rh_type, blood_component, date_to)
    if report_type == "expiry":
        return _call(fn, blood_group, rh_type, blood_component, date_to, None)
    if report_type == "alerts":
        return _call(fn, blood_group, rh_type, blood_component, date_from, date_to, None, None)
    return _call(fn, date_from, date_to)  # supply_vs_demand


# ============================================================================ CROSS-DOMAIN ANALYTIC TOOLS
def get_top_demand_items(user, domain, limit=5, category=None):
    if domain == "medicine":
        _require(user, MEDICINE_ROLES, "medicine")
        return _call(msvc.demand_rankings, None, category, None, None, limit)
    _require(user, BLOOD_ROLES, "blood")
    return _call(bsvc.demand_rankings, None, None, None, None, None, limit)


def get_low_stock_items(user, domain, category=None):
    """Returns items with stock_status in (Low, Critical). Two calls (one per status) because the
    underlying service filters by a single status; results are merged here, not computed differently."""
    if domain == "medicine":
        _require(user, MEDICINE_ROLES, "medicine")
        low = _call(misvc.inventory, "Low", None, category, None, None, None, "asc", 100, 0)
        crit = _call(misvc.inventory, "Critical", None, category, None, None, None, "asc", 100, 0)
    else:
        _require(user, BLOOD_ROLES, "blood")
        low = _call(bisvc.inventory, "Low", None, None, None, None, "asc", 100, 0)
        crit = _call(bisvc.inventory, "Critical", None, None, None, None, "asc", 100, 0)
    if "error" in low or "error" in crit:
        return low if "error" in low else crit
    return {"low": low.get("items", []), "critical": crit.get("items", []),
            "total": low.get("total", 0) + crit.get("total", 0)}


def get_near_expiry_items(user, domain, medicine_id=None, blood_group=None, rh_type=None, blood_component=None):
    if domain == "medicine":
        _require(user, MEDICINE_ROLES, "medicine")
        return _call(mesvc.expiry_list, "Near Expiry", medicine_id, None, None, None, None, None, None, None,
                     "days_remaining", "asc", 50, 0)
    _require(user, BLOOD_ROLES, "blood")
    return _call(besvc.expiry_list, "Near Expiry", blood_group, rh_type, blood_component, None, None, None, None,
                 None, "days_remaining", "asc", 50, 0)


def get_shortage_risk(user, domain, medicine_id=None, category=None, blood_group=None, rh_type=None,
                      blood_component=None, horizon_days=None):
    """Forecast-based recommendations, filtered to Potential Shortage only."""
    if domain == "medicine":
        result = get_medicine_forecast_recommendations(user, medicine_id, category, horizon_days)
    else:
        result = get_blood_forecast_recommendations(user, blood_group, rh_type, blood_component, horizon_days)
    if "error" in result or not result.get("available"):
        return result
    shortage_items = [i for i in result["items"] if i["recommendation_type"] == "Potential Shortage"]
    return {**result, "items": shortage_items, "total": len(shortage_items)}


def calculate_supply_demand_difference(user, date_from=None, date_to=None):
    _require(user, BLOOD_ROLES, "blood")
    result = _call(bsvc.supply_vs_demand, date_from, date_to)
    return result


def explain_metric(user, metric_name):
    """General ML-terminology glossary -- not project data, so no RBAC/service call needed."""
    defs = {
        "rmse": "RMSE (Root Mean Squared Error) measures the typical size of prediction errors in the same units as "
                "the demand being forecast, with larger errors penalized more heavily than smaller ones. Lower is better.",
        "mae": "MAE (Mean Absolute Error) is the average absolute difference between predicted and actual demand, in "
               "the same units as demand. Unlike RMSE it weights all errors equally. Lower is better.",
        "r2": "R² (R-squared) indicates the proportion of variation in actual demand that the model's predictions "
              "explain, from 0 to 1 (values can go negative for a very poor fit). Closer to 1 is better.",
    }
    key = metric_name.strip().lower().replace("-", "").replace(" ", "")
    if key in ("r2", "rsquared", "rsq"):
        key = "r2"
    return {"metric": metric_name, "definition": defs.get(key, "Unknown metric; supported: RMSE, MAE, R2.")}


TOOL_REGISTRY = {
    "get_medicine_inventory": get_medicine_inventory, "get_medicine_demand": get_medicine_demand,
    "get_medicine_demand_summary": get_medicine_demand_summary, "get_medicine_trends": get_medicine_trends,
    "get_medicine_growth": get_medicine_growth, "get_medicine_movement": get_medicine_movement,
    "get_medicine_forecast": get_medicine_forecast, "get_medicine_backtest": get_medicine_backtest,
    "get_medicine_model_comparison": get_medicine_model_comparison, "get_medicine_expiry": get_medicine_expiry,
    "get_medicine_alerts": get_medicine_alerts, "get_medicine_recommendations": get_medicine_recommendations,
    "get_medicine_forecast_recommendations": get_medicine_forecast_recommendations,
    "get_medicine_report": get_medicine_report,
    "get_blood_inventory": get_blood_inventory, "get_blood_demand": get_blood_demand,
    "get_blood_demand_summary": get_blood_demand_summary, "get_blood_supply": get_blood_supply,
    "get_blood_supply_vs_demand": get_blood_supply_vs_demand, "get_blood_trends": get_blood_trends,
    "get_blood_growth": get_blood_growth, "get_blood_movement": get_blood_movement,
    "get_blood_forecast": get_blood_forecast, "get_blood_backtest": get_blood_backtest,
    "get_blood_model_comparison": get_blood_model_comparison, "get_blood_expiry": get_blood_expiry,
    "get_blood_alerts": get_blood_alerts, "get_blood_recommendations": get_blood_recommendations,
    "get_blood_forecast_recommendations": get_blood_forecast_recommendations, "get_blood_report": get_blood_report,
    "get_top_demand_items": get_top_demand_items, "get_low_stock_items": get_low_stock_items,
    "get_near_expiry_items": get_near_expiry_items, "get_shortage_risk": get_shortage_risk,
    "calculate_supply_demand_difference": calculate_supply_demand_difference, "explain_metric": explain_metric,
}


def execute_tool(name, user, **kwargs):
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return fn(user, **kwargs)
    except ToolAuthorizationError as e:
        return {"error": f"not_authorized", "domain": e.domain}
    except TypeError as e:
        return {"error": f"Invalid parameters for {name}: {e}"}
