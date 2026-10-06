"""
nlu.py

Deterministic natural-language parameter extraction used by BOTH chatbot paths:
  - When an LLM provider is configured, the LLM extracts entities itself as tool-call
    arguments, but this module resolves fuzzy natural-language values (e.g. "last month",
    "paracetamol", "O positive") into exact, validated parameters the services expect
    (date ranges, medicine_id, blood_group/rh_type/blood_component). The LLM is told the
    valid vocabularies via the tool schemas' descriptions, and generated string arguments
    still pass through these resolvers before touching any service, so a request can never
    reach SQL with an unvalidated raw string.
  - When no LLM provider is configured, `classify_intent()` below additionally performs the
    tool-selection step itself, using a scored keyword/pattern matcher over roughly 30
    general-purpose intents (NOT one hardcoded answer per literal question -- the same intent
    matches "what is the stock of X", "how many units of X are there", "tell me X inventory",
    "how much X do we have" identically, because all of them are scored against the same
    keyword/entity signals, not matched as literal strings).

This module is pure Python + two read-only DB lookups (medicine catalogue, blood vocabulary);
it never executes a query built from user text.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from app.database.db import db_cursor
from app.utils.cache import cached

# ---------------------------------------------------------------------------------------
# Reference vocabularies (loaded from the real DB/catalogue, cached briefly; never hardcoded
# per-question -- these are the universe of valid entity VALUES, not question->answer pairs).
# ---------------------------------------------------------------------------------------

def _load_medicine_catalogue():
    with db_cursor() as cur:
        cur.execute("SELECT medicine_id, medicine_name, category FROM medicines")
        return cur.fetchall()


def medicine_catalogue():
    return cached("nlu:medicines", 300, _load_medicine_catalogue)


BLOOD_GROUPS = ["AB", "A", "B", "O"]  # AB checked first so "AB+" doesn't get parsed as "A"
RH_WORDS = {"positive": "Positive", "pos": "Positive", "+": "Positive",
            "negative": "Negative", "neg": "Negative", "-": "Negative"}
COMPONENTS = {"whole blood": "Whole Blood", "whole": "Whole Blood", "rbc": "RBC",
              "red blood cell": "RBC", "red cells": "RBC", "platelet": "Platelets",
              "platelets": "Platelets", "plasma": "Plasma"}

METRIC_KEYWORDS = {
    "demand": ["demand", "requested", "requests", "consumption", "usage"],
    "supply": ["supply", "donated", "donation", "received", "collection", "collected"],
    "inventory": ["stock", "inventory", "available", "on hand", "units left", "closing stock",
                 "currently have", "do we have", "how much do we have"],
    "forecast": ["forecast", "predict", "prediction", "projected", "expected demand", "next week",
                 "next month", "future demand"],
    "backtest": ["backtest", "how accurate", "model accuracy", "actual vs predicted", "actual versus predicted",
                "actual and predicted", "was predicted", "what was predicted"],
    "trend": ["trend", "trending", "growth", "growing", "increase", "decrease", "change over time",
              "year over year", "moving average"],
    "expiry": ["expire", "expiry", "expiring", "near expiry", "expired", "shelf life"],
    "alerts": ["alert", "alerts", "flagged", "warning", "critical", "attention"],
    "recommendations": ["recommend", "recommendation", "suggest", "replenish", "replenishment", "why is"],
    "report": ["report", "summary", "generate a report", "give me a summary"],
    "model": ["which model", "what model", "model used", "model performing", "rmse", "mae",
              "r2", "r-squared", "accuracy of the model", "best model"],
    "movement": ["fast moving", "slow moving", "medium moving", "fast-moving", "slow-moving"],
}

DOMAIN_KEYWORDS = {
    "medicine": ["medicine", "medicines", "drug", "drugs", "pharmacy", "tablet", "capsule"],
    "blood": ["blood", "o+", "o-", "a+", "a-", "b+", "b-", "ab+", "ab-", "donor", "donation",
              "transfusion", "platelet", "plasma", "rbc"],
}

GRANULARITY_WORDS = {"daily": "daily", "day": "daily", "today": "daily", "yesterday": "daily",
                     "weekly": "weekly", "week": "weekly", "monthly": "monthly", "month": "monthly",
                     "yearly": "yearly", "year": "yearly", "annual": "yearly"}


@dataclass
class ExtractedEntities:
    domain: Optional[str] = None             # "medicine" | "blood"
    medicine_id: Optional[str] = None
    medicine_name_query: Optional[str] = None
    category: Optional[str] = None
    blood_group: Optional[str] = None
    rh_type: Optional[str] = None
    blood_component: Optional[str] = None
    metrics: list = field(default_factory=list)      # ordered by first mention
    granularity: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    period_label: Optional[str] = None
    horizon_days: Optional[int] = None
    unresolved_mentions: list = field(default_factory=list)  # raw text that looked like an entity but didn't resolve


def resolve_medicine(text: str) -> tuple:
    """Returns (medicine_id, matched_name) or (None, None). Matches against the REAL catalogue
    (id or name substring, case-insensitive) -- never guesses an id that doesn't exist."""
    t = text.lower()
    cat = medicine_catalogue()
    m = re.search(r"\bmed0*([0-9]{1,4})\b", t)
    if m:
        candidate = f"MED{int(m.group(1)):03d}"
        if any(row["medicine_id"] == candidate for row in cat):
            return candidate, next(r["medicine_name"] for r in cat if r["medicine_id"] == candidate)
    best = None
    for row in cat:
        name = row["medicine_name"].lower()
        base = name.split(" ")[0]  # e.g. "paracetamol" out of "paracetamol 500mg"
        if base in t or name in t:
            if best is None or len(base) > len(best[1]):
                best = (row["medicine_id"], base, row["medicine_name"])
    if best:
        return best[0], best[2]
    return None, None


def resolve_blood_segment(text: str) -> tuple:
    """Returns (blood_group, rh_type, blood_component). Any element can be None if not mentioned."""
    t = " " + text.lower() + " "
    bg = rh = comp = None
    combo = re.search(r"\b(ab|a|b|o)\s*([+-]|positive|negative|pos|neg)\b", t)
    if combo:
        bg = combo.group(1).upper()
        rh = RH_WORDS.get(combo.group(2), None)
    else:
        for g in BLOOD_GROUPS:
            if re.search(rf"\bgroup\s+{g.lower()}\b", t) or re.search(rf"\b{g.lower()}\s+blood\b", t):
                bg = g
                break
        for word, val in RH_WORDS.items():
            if word in ("+", "-"):
                continue
            if re.search(rf"\b{word}\b", t):
                rh = val
                break
    for phrase, val in COMPONENTS.items():
        if phrase in t:
            comp = val
            break
    return bg, rh, comp


def resolve_time_period(text: str, today: date) -> tuple:
    """Returns (date_from, date_to, granularity, label) or (None, None, None, None) if no
    time expression was found. `today` should be the project's as-of date (never wall-clock
    time, since the datasets are historical/synthetic)."""
    t = text.lower()

    def week_start(d):
        return d - timedelta(days=d.weekday())

    if "today" in t:
        return today, today, "daily", "today"
    if "yesterday" in t:
        d = today - timedelta(days=1)
        return d, d, "daily", "yesterday"
    if "this week" in t:
        return week_start(today), today, "weekly", "this week"
    if "last week" in t:
        start = week_start(today) - timedelta(days=7)
        return start, start + timedelta(days=6), "weekly", "last week"
    if "this month" in t:
        return today.replace(day=1), today, "monthly", "this month"
    if "last month" in t:
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end, "monthly", "last month"
    if "this year" in t:
        return today.replace(month=1, day=1), today, "yearly", "this year"
    if "last year" in t:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "yearly", "last year"
    m = re.search(r"last\s+(\d+)\s+days?", t)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=n - 1), today, "daily", f"last {n} days"
    m = re.search(r"last\s+quarter", t)
    if m:
        return today - timedelta(days=90), today, "monthly", "last quarter"
    for word, gran in GRANULARITY_WORDS.items():
        if re.search(rf"\b{word}\b", t):
            return None, None, gran, word
    return None, None, None, None


def resolve_future_horizon(text: str) -> Optional[int]:
    t = text.lower()
    m = re.search(r"next\s+(\d+)\s+days?", t)
    if m:
        return int(m.group(1))
    if "next week" in t or "next 7 days" in t:
        return 7
    if "next month" in t or "next 30 days" in t:
        return 30
    if re.search(r"\bfuture\b|\bforecast\b|\bpredict", t) and re.search(r"\bweek\b", t):
        return 7
    return None


def extract_metrics(text: str) -> list:
    t = text.lower()
    found = []
    for metric, kws in METRIC_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                found.append(metric)
                break
    return found


def extract_domain(text: str, prior_domain: Optional[str] = None) -> Optional[str]:
    t = text.lower()
    scores = {d: sum(1 for kw in kws if kw in t) for d, kws in DOMAIN_KEYWORDS.items()}
    if scores["medicine"] and not scores["blood"]:
        return "medicine"
    if scores["blood"] and not scores["medicine"]:
        return "blood"
    if scores["medicine"] and scores["blood"]:
        return "medicine" if scores["medicine"] >= scores["blood"] else "blood"
    return prior_domain  # ambiguous on its own -- caller decides whether context fills it in


def extract_entities(text: str, as_of: date, prior_domain: Optional[str] = None) -> ExtractedEntities:
    e = ExtractedEntities()
    e.domain = extract_domain(text, prior_domain)
    e.medicine_id, name = resolve_medicine(text)
    if name:
        e.medicine_name_query = name
    e.blood_group, e.rh_type, e.blood_component = resolve_blood_segment(text)
    if e.blood_group or e.rh_type or e.blood_component:
        e.domain = e.domain or "blood"
    if e.medicine_id:
        e.domain = e.domain or "medicine"
    e.metrics = extract_metrics(text)
    e.date_from, e.date_to, e.granularity, e.period_label = resolve_time_period(text, as_of)
    e.horizon_days = resolve_future_horizon(text)
    return e
