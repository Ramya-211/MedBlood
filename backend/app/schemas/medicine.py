"""Enumerations / small models used to validate Medicine API query parameters."""

from enum import Enum


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


class TrendDirection(str, Enum):
    increasing = "Increasing"
    decreasing = "Decreasing"
    stable = "Stable"


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


class AnomalyType(str, Enum):
    spike = "Demand Spike"
    drop = "Demand Drop"
    unusual = "Unusual Pattern"


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


class GrowthPeriod(str, Enum):
    week = "week"
    month = "month"
