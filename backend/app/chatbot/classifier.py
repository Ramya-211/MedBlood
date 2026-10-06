"""
classifier.py

Deterministic fallback intent classifier, used only when no LLM provider is configured
(NullProvider). This is NOT a static FAQ: it does not match literal question strings. It scores
the SAME signals (domain, metric keywords, resolved entities, phrase patterns like "why"/
"compare"/"top"/"low stock") that app/chatbot/nlu.py extracts from arbitrary phrasing, and maps
the winning signal combination to one of ~25 general-purpose tool calls. "What is the stock of
MED001?", "How many units of MED001 are available?", "Tell me MED001 inventory." and "How much
MED001 do we currently have?" all land on the same intent (medicine_inventory) because they all
trigger the same inventory keyword/entity signals -- not because any of those exact sentences
is listed anywhere.

When an LLM provider IS configured, this module is not used for routing at all; the LLM chooses
the tool via tool_schemas.TOOL_SCHEMAS. This module still supplies the resolved entities either way.
"""

import re
from dataclasses import dataclass
from typing import Optional

INJECTION_PATTERNS = [
    r"ignore (all |your |previous |the )?(instructions|prompt|rules)",
    r"system prompt", r"api[\s_-]?key", r"database password", r"db password",
    r"credentials", r"reveal your (instructions|prompt)", r"show me the password",
    r"act as (dan|jailbreak)", r"disregard (all |your )?(instructions|rules)",
]

MEDICAL_ADVICE_PATTERNS = [
    r"\bdiagnos", r"\bprescri", r"\bshould i take\b", r"\btreat(ment)? for\b",
    r"\bdosage for (my|a) (patient|child|baby)\b", r"\bwhat medicine (should|do) i (give|take)\b",
    r"\bis it safe to transfuse\b", r"\bclinical decision\b",
]

GREETING_PATTERNS = [r"^\s*(hi|hello|hey|good (morning|afternoon|evening))[\s!.]*$"]


@dataclass
class RoutingDecision:
    kind: str                      # "tool" | "clarify" | "out_of_scope" | "medical_safety" | "greeting" | "injection_blocked"
    tool: Optional[str] = None
    args: Optional[dict] = None
    intent: Optional[str] = None
    clarification: Optional[str] = None
    sanitized_text: Optional[str] = None


def detect_injection(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in INJECTION_PATTERNS)


def detect_medical_advice(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in MEDICAL_ADVICE_PATTERNS)


def detect_greeting(text: str) -> bool:
    t = text.lower()
    return any(re.match(p, t) for p in GREETING_PATTERNS)


def _wants(text: str, *phrases) -> bool:
    t = text.lower()
    return any(p in t for p in phrases)


def classify(text: str, entities) -> RoutingDecision:
    """entities: nlu.ExtractedEntities, already merged with conversation focus."""
    t = text.lower()
    domain = entities.domain
    metrics = entities.metrics

    # --- General ML-terminology questions never need a medicine/blood domain ---
    if _wants(t, "rmse", "mae", "r-squared", "r2", "what does rmse", "what does mae", "r² ",
             "difference between mae and rmse"):
        normalized = t.replace("²", "2").replace("-", "")
        for name in ("rmse", "mae", "r2"):
            if name in normalized:
                return RoutingDecision("tool", "explain_metric", {"metric_name": name}, "explain_metric")

    # --- Out of scope: no domain signal, no metric signal, not a greeting ---
    if not domain and not metrics and not _wants(t, "report", "summary", "alert", "recommend"):
        return RoutingDecision(kind="out_of_scope")

    if domain is None:
        return RoutingDecision(kind="clarify", clarification="Do you want medicine information or blood information?")

    seg_kwargs = ({"medicine_id": entities.medicine_id, "category": entities.category} if domain == "medicine"
                  else {"blood_group": entities.blood_group, "rh_type": entities.rh_type,
                       "blood_component": entities.blood_component})

    # --- Cross-cutting analytic patterns (checked before plain metric routing) ---
    if _wants(t, "top", "highest demand", "most demand", "which medicine had the highest", "which blood group has the highest"):
        return RoutingDecision("tool", "get_top_demand_items", {"domain": domain, "category": entities.category},
                               "top_demand_items")
    if _wants(t, "low stock", "low in stock", "running low", "need replenish"):
        return RoutingDecision("tool", "get_low_stock_items", {"domain": domain, "category": entities.category},
                               "low_stock_items")
    if _wants(t, "near expiry", "expiring soon", "about to expire", "expire first"):
        return RoutingDecision("tool", "get_near_expiry_items", {"domain": domain, **seg_kwargs}, "near_expiry_items")
    if _wants(t, "shortage", "risk of running out", "likely to face shortages", "may face shortage"):
        return RoutingDecision("tool", "get_shortage_risk",
                               {"domain": domain, **seg_kwargs, "horizon_days": entities.horizon_days},
                               "shortage_risk")
    if domain == "blood" and _wants(t, "supply and demand", "supply vs demand", "supply versus demand",
                                    "requested with received", "received with requested"):
        return RoutingDecision("tool", "get_blood_supply_vs_demand",
                               {"date_from": _s(entities.date_from), "date_to": _s(entities.date_to)}, "supply_vs_demand")
    if _wants(t, "which model", "what model", "model performing", "best model", "model used"):
        tool = "get_medicine_model_comparison" if domain == "medicine" else "get_blood_model_comparison"
        return RoutingDecision("tool", tool, {}, "model_comparison")
    if _wants(t, "fast moving", "slow moving", "medium moving", "fast-moving", "slow-moving"):
        tool = "get_medicine_movement" if domain == "medicine" else "get_blood_movement"
        tier = "Fast Moving" if "fast" in t else ("Slow Moving" if "slow" in t else "Medium Moving")
        args = {"tier": tier} if domain == "medicine" else {}
        return RoutingDecision("tool", tool, args, "movement_classification")
    if _wants(t, "why", "reason") and _wants(t, "recommend", "flagged", "alert", "shortage", "low stock", "critical"):
        tool = "get_medicine_recommendations" if domain == "medicine" else "get_blood_recommendations"
        return RoutingDecision("tool", tool, seg_kwargs, "explain_recommendation")

    # --- Report / summary ---
    if _wants(t, "report", "generate a summary", "give me a summary", "summary of"):
        rtype = "demand"
        for m in ("inventory", "forecast", "expiry", "alerts", "recommendations"):
            if m in t:
                rtype = m
                break
        tool = "get_medicine_report" if domain == "medicine" else "get_blood_report"
        return RoutingDecision("tool", tool, {"report_type": rtype, **seg_kwargs,
                                              "date_from": _s(entities.date_from), "date_to": _s(entities.date_to)},
                               f"{domain}_report")

    # --- Growth / trend ---
    if "growth" in metrics or _wants(t, "growth", "grown", "biggest increase"):
        period = "week" if _wants(t, "week") else "month"
        tool = "get_medicine_growth" if domain == "medicine" else "get_blood_growth"
        return RoutingDecision("tool", tool, {**seg_kwargs, "period": period}, "growth")
    if "trend" in metrics or _wants(t, "trend", "trending", "changed over"):
        tool = "get_medicine_trends" if domain == "medicine" else "get_blood_trends"
        return RoutingDecision("tool", tool, seg_kwargs, "trend")

    # --- Forecast vs backtest vs demand (must not conflate) ---
    # Backtest checked first: "actual vs predicted" / "how accurate was X" is unambiguously
    # about historical performance even though the word "predicted" also appears in forecast talk.
    if "backtest" in metrics or _wants(t, "was predicted", "how accurate", "actual vs predicted", "actual versus predicted",
                                       "actual and predicted"):
        tool = "get_medicine_backtest" if domain == "medicine" else "get_blood_backtest"
        return RoutingDecision("tool", tool, {**seg_kwargs, "date_from": _s(entities.date_from),
                                              "date_to": _s(entities.date_to)}, "backtest")
    if "forecast" in metrics or entities.horizon_days or _wants(t, "will be", "next week", "next month", "next 7",
                                                                "next 30", "expected demand"):
        tool = "get_medicine_forecast" if domain == "medicine" else "get_blood_forecast"
        return RoutingDecision("tool", tool, {**seg_kwargs, "horizon": entities.horizon_days}, "future_forecast")

    # --- Expiry / alerts / recommendations / inventory / supply / demand (plain) ---
    if "expiry" in metrics:
        tool = "get_medicine_expiry" if domain == "medicine" else "get_blood_expiry"
        status = "Expired" if "expired" in t else None
        return RoutingDecision("tool", tool, {**seg_kwargs, "status": status}, "expiry")
    if "alerts" in metrics:
        tool = "get_medicine_alerts" if domain == "medicine" else "get_blood_alerts"
        severity = "Critical" if "critical" in t else None
        return RoutingDecision("tool", tool, {**seg_kwargs, "severity": severity}, "alerts")
    if "recommendations" in metrics:
        tool = "get_medicine_recommendations" if domain == "medicine" else "get_blood_recommendations"
        return RoutingDecision("tool", tool, seg_kwargs, "recommendations")
    if "inventory" in metrics:
        tool = "get_medicine_inventory" if domain == "medicine" else "get_blood_inventory"
        return RoutingDecision("tool", tool, seg_kwargs, "inventory")
    if domain == "blood" and "supply" in metrics:
        return RoutingDecision("tool", "get_blood_supply", {"date_from": _s(entities.date_from),
                                                            "date_to": _s(entities.date_to)}, "supply")
    if "demand" in metrics or True:  # default: a domain was identified but metric is unclear -> treat as demand
        if not entities.granularity and not (entities.date_from and entities.date_to):
            return RoutingDecision(kind="clarify",
                                   clarification="Would you like daily, weekly, monthly, or yearly demand?")
        gran = entities.granularity or "daily"
        tool = "get_medicine_demand" if domain == "medicine" else "get_blood_demand"
        return RoutingDecision("tool", tool, {**seg_kwargs, "granularity": gran,
                                              "date_from": _s(entities.date_from), "date_to": _s(entities.date_to)}, "demand")


def _s(d):
    return d.isoformat() if d else None
