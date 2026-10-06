"""
conversation.py

Persists chat turns (chat_conversations / chat_messages) and maintains a small structured
"focus" per conversation so follow-up questions work without the user repeating themselves:

    USER: How much O+ blood is available?
    ASSISTANT: ...
    USER: What about its demand?        <- "its" resolves to O+ via focus.blood_group/rh_type
    USER: And next month?               <- metric stays "demand", only the time period changes
    USER: Why is it increasing?         <- "it" resolves to the last metric discussed (demand)

The focus holds only entity references (medicine_id, blood segment, metric, date range) --
never secrets, credentials, or full tool payloads.
"""

import json
import uuid
from datetime import date, datetime, timedelta

from app.config import get_settings
from app.database.db import db_cursor


def new_conversation(user_id: int) -> str:
    conv_id = str(uuid.uuid4())
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO chat_conversations (id, user_id, context_state) VALUES (%s, %s, %s)",
                   (conv_id, user_id, json.dumps({})))
    return conv_id


def _row_to_focus(row):
    if not row or not row["context_state"]:
        return {}
    v = row["context_state"]
    return json.loads(v) if isinstance(v, (str, bytes)) else v


def get_conversation(conv_id: str, user_id: int):
    """Returns the conversation row if it belongs to this user, else None (never lets a user
    read or extend someone else's conversation by guessing an id)."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM chat_conversations WHERE id = %s AND user_id = %s", (conv_id, user_id))
        return cur.fetchone()


def get_or_create(conv_id, user_id: int) -> tuple:
    """Returns (conversation_id, focus_dict, is_new)."""
    if conv_id:
        row = get_conversation(conv_id, user_id)
        if row:
            ttl = get_settings().chat_context_ttl_minutes
            if datetime.now() - row["last_message_at"] > timedelta(minutes=ttl):
                return conv_id, {}, False  # context expired, but keep the same thread/history
            return conv_id, _row_to_focus(row), False
    return new_conversation(user_id), {}, True


def recent_messages(conv_id: str, limit: int = None) -> list:
    limit = limit or get_settings().chat_context_turns
    with db_cursor() as cur:
        cur.execute("SELECT role, content, created_at FROM chat_messages WHERE conversation_id = %s "
                    "ORDER BY created_at DESC, id DESC LIMIT %s", (conv_id, limit * 2))
        rows = cur.fetchall()
    return list(reversed(rows))


def save_turn(conv_id: str, user_message: str, assistant_message: str, intent: str, tool_calls: list, focus: dict):
    def default(o):
        if isinstance(o, date):
            return o.isoformat()
        raise TypeError

    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO chat_messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
                   (conv_id, user_message))
        cur.execute("INSERT INTO chat_messages (conversation_id, role, content, intent, tool_calls) "
                    "VALUES (%s, 'assistant', %s, %s, %s)",
                    (conv_id, assistant_message, intent, json.dumps(tool_calls, default=default)))
        cur.execute("UPDATE chat_conversations SET last_message_at = CURRENT_TIMESTAMP, context_state = %s WHERE id = %s",
                   (json.dumps(focus, default=default), conv_id))


def merge_focus(prior: dict, entities) -> dict:
    """Fold newly-extracted entities into the running focus. A new mention always wins; an
    unmentioned slot carries over from the prior turn (this is what makes "its demand" and
    "and next month" resolve correctly without repeating the whole question)."""
    focus = dict(prior or {})
    if entities.domain:
        focus["domain"] = entities.domain
    if entities.medicine_id:
        focus["medicine_id"] = entities.medicine_id
        focus.pop("blood_group", None); focus.pop("rh_type", None); focus.pop("blood_component", None)
    if entities.blood_group or entities.rh_type or entities.blood_component:
        focus["blood_group"] = entities.blood_group or focus.get("blood_group")
        focus["rh_type"] = entities.rh_type or focus.get("rh_type")
        focus["blood_component"] = entities.blood_component or focus.get("blood_component")
        focus.pop("medicine_id", None)
    if entities.category:
        focus["category"] = entities.category
    if entities.metrics:
        focus["last_metric"] = entities.metrics[0]
    if entities.date_from and entities.date_to:
        focus["date_from"] = entities.date_from.isoformat()
        focus["date_to"] = entities.date_to.isoformat()
        focus["period_label"] = entities.period_label
    elif entities.granularity:
        focus["granularity"] = entities.granularity
        focus.pop("date_from", None); focus.pop("date_to", None)
    if entities.horizon_days:
        focus["horizon_days"] = entities.horizon_days
    return focus


def apply_focus_to_entities(entities, focus: dict):
    """Fills in gaps in a freshly-extracted entity set using the running focus, WITHOUT
    overwriting anything the user just mentioned explicitly in this turn."""
    if not focus:
        return entities
    entities.domain = entities.domain or focus.get("domain")
    if not entities.medicine_id and not (entities.blood_group or entities.rh_type or entities.blood_component):
        entities.medicine_id = entities.medicine_id or focus.get("medicine_id")
        entities.blood_group = entities.blood_group or focus.get("blood_group")
        entities.rh_type = entities.rh_type or focus.get("rh_type")
        entities.blood_component = entities.blood_component or focus.get("blood_component")
    entities.category = entities.category or focus.get("category")
    if not entities.metrics and focus.get("last_metric"):
        entities.metrics = [focus["last_metric"]]
    if not entities.date_from and not entities.granularity:
        if focus.get("date_from"):
            entities.date_from = date.fromisoformat(focus["date_from"])
            entities.date_to = date.fromisoformat(focus["date_to"])
            entities.period_label = focus.get("period_label")
        elif focus.get("granularity"):
            entities.granularity = focus["granularity"]
    entities.horizon_days = entities.horizon_days or focus.get("horizon_days")
    return entities
