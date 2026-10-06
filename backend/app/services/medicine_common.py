"""Shared helpers for the Medicine services: as-of date, entity validation, response metadata."""

from app.config import get_settings
from app.database.db import db_cursor
from app.database.queries import medicine_demand_queries as dq
from app.utils.cache import cached
from app.utils.errors import BadRequestError, NotFoundError
from app.utils.query_helpers import parse_date

PROVENANCE = "SYNTHETIC"
PROVENANCE_NOTE = ("All medicine data is SYNTHETIC (created for this academic project). "
                   "It is not real hospital, pharmacy or patient data.")

# Documented rule behind the supplied stock_status values (see MEDICINE_DATA_DICTIONARY.md):
# days_of_cover = closing_stock / average daily units_issued over the 30 days ending that date.
STOCK_RULE = {
    "critical_below_days": 3, "low_below_days": 7, "overstock_above_days": 45,
    "definition": ("days_of_cover = closing_stock / mean(units_issued over the 30 days ending at the as-of date). "
                   "Critical: < 3 days, Low: < 7 days, Overstock: > 45 days, otherwise Normal. "
                   "stock_status values are the ones supplied with the dataset."),
}

ALERT_VOCABULARY = ["Low Stock", "Critical Stock", "Potential Shortage", "Overstock", "Near Expiry", "Expired",
                    "Demand Spike", "Demand Drop", "Increasing Demand", "Anomaly"]


def as_of_date():
    """The 'current' date for stock/expiry logic. The datasets are synthetic and end on a fixed date, so this is the
    latest date present in the data (or AS_OF_DATE from the environment) -- never today's wall-clock date."""
    settings = get_settings()
    if settings.as_of_date_override:
        return parse_date(settings.as_of_date_override, "AS_OF_DATE")

    def load():
        with db_cursor() as cur:
            return dq.latest_inventory_date(cur)

    d = cached("med:as_of", 60, load)
    if d is None:
        raise NotFoundError("No medicine inventory data has been imported yet.")
    return d


def resolve_as_of(as_of_param):
    return parse_date(as_of_param, "as_of") or as_of_date()


def near_expiry_days(param=None):
    days = param if param is not None else get_settings().near_expiry_days
    if not 1 <= days <= 730:
        raise BadRequestError("near_expiry_days must be between 1 and 730.")
    return days


def validate_entities(cur, medicine_id=None, category=None):
    if medicine_id and not dq.get_medicine(cur, medicine_id):
        raise NotFoundError(f"Medicine '{medicine_id}' was not found.")
    if category and not dq.category_exists(cur, category):
        raise NotFoundError(f"Category '{category}' was not found.")


def meta(as_of=None, **extra):
    out = {"data_provenance": PROVENANCE, "note": PROVENANCE_NOTE}
    if as_of is not None:
        out["as_of_date"] = as_of
    out.update(extra)
    return out
