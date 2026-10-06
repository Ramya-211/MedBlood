"""Shared helpers for Blood services. Mirrors medicine_common.py."""

from app.config import get_settings
from app.database.db import db_cursor
from app.database.queries import blood_demand_queries as dq
from app.utils.cache import cached
from app.utils.errors import BadRequestError, NotFoundError
from app.utils.query_helpers import parse_date

PROVENANCE_DEMAND = "SYNTHETIC"
PROVENANCE_SUPPLY = "SYNTHETIC_PLACEHOLDER"
PROVENANCE_NOTE = ("Blood DEMAND (units requested) and INVENTORY/EXPIRY data are SYNTHETIC, created for this academic "
                   "project. Blood SUPPLY/COLLECTION data is a SYNTHETIC PLACEHOLDER: no real donation dataset was "
                   "ever supplied (see BLOOD_DATA_REPORT.md). None of this represents real hospital or blood-bank "
                   "records.")

# Documented rule behind blood stock status (see backend data/blood_data/scripts/generate_recommendations_and_alerts.py):
STOCK_RULE = {
    "critical_below_days": 2, "low_below_days": 5, "overstock_above_days": 30,
    "definition": ("days_of_cover = closing_stock / mean(units_issued over the 30 days ending at the as-of date). "
                   "Critical: < 2 days, Low: < 5 days, Overstock: > 30 days, otherwise Normal. blood_inventory has "
                   "no stored stock_status column, so this status is derived here using the exact thresholds "
                   "documented in the original blood-data generation scripts."),
}
NEAR_EXPIRY_DEFAULT_DAYS = 5  # documented default used when the blood dataset was generated (shorter shelf life than medicine)

ALERT_VOCABULARY = ["Low Stock", "Critical Stock", "Potential Shortage", "Overstock", "Near Expiry", "Expired",
                    "Demand Increase", "Demand Anomaly"]


def as_of_date():
    def load():
        with db_cursor() as cur:
            return dq.latest_inventory_date(cur)

    d = cached("blood:as_of", 60, load)
    if d is None:
        raise NotFoundError("No blood inventory data has been imported yet.")
    return d


def resolve_as_of(as_of_param):
    return parse_date(as_of_param, "as_of") or as_of_date()


def near_expiry_days(param=None):
    days = param if param is not None else get_settings().near_expiry_days
    # Blood's dataset default (5) differs from medicine's config default (30); an explicit
    # override always wins, otherwise fall back to the blood-specific documented default.
    if param is None and days == 30:
        days = NEAR_EXPIRY_DEFAULT_DAYS
    if not 1 <= days <= 365:
        raise BadRequestError("near_expiry_days must be between 1 and 365.")
    return days


def validate_segment(cur, blood_group=None, rh_type=None, blood_component=None):
    if (blood_group or rh_type or blood_component) and not dq.segment_exists(cur, blood_group, rh_type, blood_component):
        parts = [p for p in (blood_group, rh_type, blood_component) if p]
        raise NotFoundError(f"No blood demand records found for {' / '.join(parts)}.")


def meta(as_of=None, **extra):
    out = {"data_provenance": {"demand_inventory_expiry": PROVENANCE_DEMAND, "supply_collection": PROVENANCE_SUPPLY},
           "note": PROVENANCE_NOTE}
    if as_of is not None:
        out["as_of_date"] = as_of
    out.update(extra)
    return out
