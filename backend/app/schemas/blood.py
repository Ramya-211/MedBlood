"""Enumerations used to validate Blood API query parameters. Mirrors schemas/medicine.py."""

from enum import Enum


class BloodGroup(str, Enum):
    A = "A"
    B = "B"
    AB = "AB"
    O = "O"


class RhType(str, Enum):
    positive = "Positive"
    negative = "Negative"


class BloodComponent(str, Enum):
    whole_blood = "Whole Blood"
    rbc = "RBC"
    platelets = "Platelets"
    plasma = "Plasma"


class Granularity(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class BacktestGranularity(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class VolumeTier(str, Enum):
    fast = "Fast Moving"
    medium = "Medium Moving"
    slow = "Slow Moving"


class StockStatus(str, Enum):
    critical = "Critical"
    low = "Low"
    normal = "Normal"
    overstock = "Overstock"


class ExpiryStatus(str, Enum):
    safe = "Safe"
    near = "Near Expiry"
    expired = "Expired"


class Severity(str, Enum):
    info = "Info"
    warning = "Warning"
    critical = "Critical"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class ReportType(str, Enum):
    demand = "demand"
    forecast = "forecast"
    inventory = "inventory"
    expiry = "expiry"
    alerts = "alerts"
    recommendations = "recommendations"
    supply_vs_demand = "supply_vs_demand"


class GrowthPeriod(str, Enum):
    week = "week"
    month = "month"
