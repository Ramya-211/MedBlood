"""
tool_schemas.py

OpenAI-style tool/function schemas for every tool in tools.TOOL_REGISTRY, used only when a
real LLM provider is configured (NullProvider never sees these). Generated from a compact
per-tool parameter spec rather than hand-written per tool, so the two can't drift apart --
every key in tools.TOOL_REGISTRY must have an entry here (checked by a test).
"""

MEDICINE_ID = {"type": "string", "description": "A medicine_id like MED001, if the user named a specific medicine."}
CATEGORY = {"type": "string", "description": "A medicine category (e.g. Analgesic, Antibiotic), if mentioned."}
BLOOD_GROUP = {"type": "string", "enum": ["A", "B", "AB", "O"], "description": "ABO blood group, if mentioned."}
RH_TYPE = {"type": "string", "enum": ["Positive", "Negative"], "description": "Rh factor, if mentioned."}
BLOOD_COMPONENT = {"type": "string", "enum": ["Whole Blood", "RBC", "Platelets", "Plasma"],
                   "description": "Blood component, if mentioned."}
DATE_FROM = {"type": "string", "description": "Start date YYYY-MM-DD, resolved from phrases like 'last month'."}
DATE_TO = {"type": "string", "description": "End date YYYY-MM-DD, resolved from phrases like 'last month'."}
GRANULARITY = {"type": "string", "enum": ["daily", "weekly", "monthly", "yearly"]}
HORIZON = {"type": "integer", "description": "Number of future days requested, e.g. 7 or 30."}
SEVERITY = {"type": "string", "enum": ["Info", "Warning", "Critical"]}
STOCK_STATUS = {"type": "string", "enum": ["Critical", "Low", "Normal", "Overstock"]}
EXPIRY_STATUS = {"type": "string", "enum": ["Safe", "Near Expiry", "Expired"]}
DOMAIN = {"type": "string", "enum": ["medicine", "blood"], "description": "Which part of the system the question is about."}

# tool_name -> (description, {param_name: schema_fragment}, [required_params])
_SPECS = {
    "get_medicine_inventory": ("Current medicine stock levels, optionally filtered.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "stock_status": STOCK_STATUS}, []),
    "get_medicine_demand": ("Historical medicine demand (units requested) at a given granularity.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "granularity": GRANULARITY,
         "date_from": DATE_FROM, "date_to": DATE_TO}, ["granularity"]),
    "get_medicine_demand_summary": ("KPI summary of medicine demand over a date range: totals, peak day, top/bottom medicines.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "get_medicine_trends": ("Whether each medicine's demand is Increasing, Decreasing or Stable, with growth rates.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY,
         "direction": {"type": "string", "enum": ["Increasing", "Decreasing", "Stable"]}}, []),
    "get_medicine_growth": ("Percentage change in medicine demand vs. the prior week or month.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "period": {"type": "string", "enum": ["week", "month"]}}, []),
    "get_medicine_movement": ("Fast/Medium/Slow moving medicine classification.",
        {"tier": {"type": "string", "enum": ["Fast Moving", "Medium Moving", "Slow Moving"]}, "category": CATEGORY}, []),
    "get_medicine_forecast": ("Model-generated FUTURE demand forecast (not historical).",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "horizon": HORIZON}, []),
    "get_medicine_backtest": ("HISTORICAL backtest: how accurate past predictions were vs actual demand.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "get_medicine_model_comparison": ("Which ML model is used for medicine forecasting and its RMSE/MAE/R2.", {}, []),
    "get_medicine_expiry": ("Medicine batches by expiry status (Safe/Near Expiry/Expired).",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "status": EXPIRY_STATUS}, []),
    "get_medicine_alerts": ("Current medicine alerts (low stock, near expiry, demand anomaly, etc.).",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "severity": SEVERITY, "alert_type": {"type": "string"}}, []),
    "get_medicine_recommendations": ("Supplied current-state medicine recommendations with reasons.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "recommendation_type": {"type": "string"}}, []),
    "get_medicine_forecast_recommendations": ("Recommendations computed live from the current forecast vs current stock.",
        {"medicine_id": MEDICINE_ID, "category": CATEGORY, "horizon_days": HORIZON}, []),
    "get_medicine_report": ("A full medicine report (demand/forecast/inventory/expiry/alerts/recommendations).",
        {"report_type": {"type": "string", "enum": ["demand", "forecast", "inventory", "expiry", "alerts", "recommendations"]},
         "medicine_id": MEDICINE_ID, "category": CATEGORY, "date_from": DATE_FROM, "date_to": DATE_TO}, ["report_type"]),

    "get_blood_inventory": ("Current blood stock levels, optionally filtered.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "stock_status": STOCK_STATUS}, []),
    "get_blood_demand": ("Historical blood DEMAND (units requested by patients, never donor volume).",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "granularity": GRANULARITY,
         "date_from": DATE_FROM, "date_to": DATE_TO}, ["granularity"]),
    "get_blood_demand_summary": ("KPI summary of blood demand over a date range.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT,
         "date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "get_blood_supply": ("Blood SUPPLY/collection (donation_volume) -- never demand.",
        {"blood_type": {"type": "string", "description": "Combined type like 'O+' or 'A-'."}, "granularity": GRANULARITY,
         "date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "get_blood_supply_vs_demand": ("Side-by-side comparison of blood supply, demand and current inventory.",
        {"date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "get_blood_trends": ("Whether blood demand is Increasing, Decreasing or Stable, per segment.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT}, []),
    "get_blood_growth": ("Percentage change in blood demand vs. the prior week or month.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT,
         "period": {"type": "string", "enum": ["week", "month"]}}, []),
    "get_blood_movement": ("Fast/Medium/Slow moving blood segment classification.",
        {"blood_component": BLOOD_COMPONENT}, []),
    "get_blood_forecast": ("Model-generated FUTURE blood demand forecast (not historical).",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "horizon": HORIZON}, []),
    "get_blood_backtest": ("HISTORICAL backtest: how accurate past blood demand predictions were.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT,
         "date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "get_blood_model_comparison": ("Which ML model is used for blood forecasting and its RMSE/MAE/R2.", {}, []),
    "get_blood_expiry": ("Blood batches by expiry status.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "status": EXPIRY_STATUS}, []),
    "get_blood_alerts": ("Current blood alerts.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "severity": SEVERITY,
         "alert_type": {"type": "string"}}, []),
    "get_blood_recommendations": ("Supplied current-state blood recommendations with reasons.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT,
         "recommendation_type": {"type": "string"}}, []),
    "get_blood_forecast_recommendations": ("Recommendations computed live from the current forecast vs current stock.",
        {"blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "horizon_days": HORIZON}, []),
    "get_blood_report": ("A full blood report (demand/forecast/inventory/expiry/alerts/recommendations/supply_vs_demand).",
        {"report_type": {"type": "string", "enum": ["demand", "forecast", "inventory", "expiry", "alerts",
                                                     "recommendations", "supply_vs_demand"]},
         "blood_group": BLOOD_GROUP, "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT,
         "date_from": DATE_FROM, "date_to": DATE_TO}, ["report_type"]),

    "get_top_demand_items": ("The highest-demand medicines or blood segments.",
        {"domain": DOMAIN, "limit": {"type": "integer"}, "category": CATEGORY}, ["domain"]),
    "get_low_stock_items": ("Items currently at Low or Critical stock.",
        {"domain": DOMAIN, "category": CATEGORY}, ["domain"]),
    "get_near_expiry_items": ("Items/batches currently Near Expiry.",
        {"domain": DOMAIN, "medicine_id": MEDICINE_ID, "blood_group": BLOOD_GROUP, "rh_type": RH_TYPE,
         "blood_component": BLOOD_COMPONENT}, ["domain"]),
    "get_shortage_risk": ("Items at risk of a forecast-driven shortage (Potential Shortage recommendations only).",
        {"domain": DOMAIN, "medicine_id": MEDICINE_ID, "category": CATEGORY, "blood_group": BLOOD_GROUP,
         "rh_type": RH_TYPE, "blood_component": BLOOD_COMPONENT, "horizon_days": HORIZON}, ["domain"]),
    "calculate_supply_demand_difference": ("Blood supply minus demand, by blood type, over a date range.",
        {"date_from": DATE_FROM, "date_to": DATE_TO}, []),
    "explain_metric": ("Explain what an ML evaluation metric (RMSE, MAE, R2) means in general.",
        {"metric_name": {"type": "string"}}, ["metric_name"]),
}


def build_tool_schemas() -> list:
    schemas = []
    for name, (desc, params, required) in _SPECS.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": name, "description": desc,
                "parameters": {"type": "object", "properties": params, "required": required},
            },
        })
    return schemas


TOOL_SCHEMAS = build_tool_schemas()
SPEC_NAMES = set(_SPECS.keys())
