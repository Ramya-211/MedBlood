"""
medicine.py — Medicine module routes. All endpoints require the PHARMACIST role
(matching "A Pharmacist must not access Admin routes"; Admin gets its own overview in Phase 10).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.dependencies import require_roles
from app.schemas.auth import Role
from app.schemas.medicine import (AnomalyType, BacktestGranularity, ExpiryStatus, Granularity, GrowthPeriod,
                                  ReportType, Severity, SortOrder, StockStatus, TrendDirection, VolumeTier)
from app.services import (medicine_alert_service as alert_svc, medicine_expiry_service as expiry_svc,
                          medicine_inventory_service as inv_svc, medicine_recommendation_service as rec_svc,
                          medicine_report_service as report_svc, medicine_service as svc)
from app.utils.errors import BadRequestError

router = APIRouter(prefix="/api/medicine", tags=["medicine"])
pharmacist_only = require_roles(Role.PHARMACIST)

DateQ = Query(None, description="YYYY-MM-DD")
Limit = Query(25, ge=1, le=500)
Offset = Query(0, ge=0)


# ============================================================ filters / dashboard
@router.get("/filters")
def filters(_user=Depends(pharmacist_only)):
    return svc.get_filters()


@router.get("/dashboard")
def dashboard(medicine_id: Optional[str] = None, category: Optional[str] = None, date_from: Optional[str] = DateQ,
             date_to: Optional[str] = DateQ, _user=Depends(pharmacist_only)):
    return svc.dashboard(medicine_id, category, date_from, date_to)


# ============================================================ demand analysis
@router.get("/demand")
def demand(granularity: Granularity, medicine_id: Optional[str] = None, category: Optional[str] = None,
          date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, by_medicine: bool = False,
          limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return svc.demand_series(granularity.value, medicine_id, category, date_from, date_to, by_medicine, limit, offset)


@router.get("/demand/summary")
def demand_summary(medicine_id: Optional[str] = None, category: Optional[str] = None, date_from: Optional[str] = DateQ,
                   date_to: Optional[str] = DateQ, _user=Depends(pharmacist_only)):
    return svc.demand_summary(medicine_id, category, date_from, date_to)


@router.get("/demand/rankings")
def demand_rankings(medicine_id: Optional[str] = None, category: Optional[str] = None, date_from: Optional[str] = DateQ,
                    date_to: Optional[str] = DateQ, limit: int = Query(5, ge=1, le=20), _user=Depends(pharmacist_only)):
    return svc.demand_rankings(medicine_id, category, date_from, date_to, limit)


@router.get("/demand/variability")
def demand_variability(medicine_id: Optional[str] = None, category: Optional[str] = None,
                       date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ,
                       _user=Depends(pharmacist_only)):
    return svc.demand_variability(medicine_id, category, date_from, date_to)


@router.get("/demand/moving-average")
def moving_average(window: int = Query(7, description="7, 14, 30, 60 or 90"), medicine_id: Optional[str] = None,
                   category: Optional[str] = None, date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ,
                   _user=Depends(pharmacist_only)):
    return svc.moving_average(window, medicine_id, category, date_from, date_to)


@router.get("/demand/growth")
def demand_growth(period: GrowthPeriod = GrowthPeriod.week, medicine_id: Optional[str] = None,
                  category: Optional[str] = None, _user=Depends(pharmacist_only)):
    return svc.demand_growth(period.value, medicine_id, category)


@router.get("/demand/trends")
def demand_trends(direction: Optional[TrendDirection] = None, medicine_id: Optional[str] = None,
                  category: Optional[str] = None, search: Optional[str] = None, sort: Optional[str] = None,
                  order: SortOrder = SortOrder.asc, _user=Depends(pharmacist_only)):
    return svc.demand_trends(direction.value if direction else None, medicine_id, category, search, sort, order.value)


@router.get("/demand/seasonality")
def demand_seasonality(medicine_id: Optional[str] = None, category: Optional[str] = None,
                       _user=Depends(pharmacist_only)):
    return svc.demand_seasonality(medicine_id, category)


@router.get("/demand/anomalies")
def demand_anomalies(medicine_id: Optional[str] = None, category: Optional[str] = None,
                     anomaly_type: Optional[AnomalyType] = None, date_from: Optional[str] = DateQ,
                     date_to: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.desc,
                     limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return svc.demand_anomalies(medicine_id, category, anomaly_type.value if anomaly_type else None, date_from,
                                date_to, sort, order.value, limit, offset)


@router.get("/demand/movement")
def demand_movement(tier: Optional[VolumeTier] = None, category: Optional[str] = None, search: Optional[str] = None,
                    sort: Optional[str] = None, order: SortOrder = SortOrder.desc, _user=Depends(pharmacist_only)):
    return svc.demand_movement(tier.value if tier else None, category, search, sort, order.value)


# ============================================================ forecasting
@router.get("/forecast/models")
def forecast_models(_user=Depends(pharmacist_only)):
    return svc.model_comparison()


@router.get("/forecast/runs")
def forecast_runs(_user=Depends(pharmacist_only)):
    return svc.forecast_runs()


@router.get("/forecast/backtest")
def forecast_backtest(medicine_id: Optional[str] = None, category: Optional[str] = None,
                      date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ,
                      _user=Depends(pharmacist_only)):
    return svc.backtest(medicine_id, category, date_from, date_to)


@router.get("/forecast/actual-vs-predicted")
def actual_vs_predicted(granularity: BacktestGranularity = BacktestGranularity.daily, medicine_id: Optional[str] = None,
                        category: Optional[str] = None, date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ,
                        limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return svc.actual_vs_predicted(granularity.value, medicine_id, category, date_from, date_to, limit, offset)


@router.get("/forecast/backtest/rows")
def backtest_rows(medicine_id: Optional[str] = None, category: Optional[str] = None, date_from: Optional[str] = DateQ,
                  date_to: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.asc,
                  limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return svc.backtest_rows(medicine_id, category, date_from, date_to, sort, order.value, limit, offset)


@router.get("/forecast/future")
def future_forecast(medicine_id: Optional[str] = None, category: Optional[str] = None,
                    run_id: Optional[int] = None, horizon: Optional[int] = Query(None, ge=1),
                    limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return svc.future_forecast(medicine_id, category, run_id, horizon, limit, offset)


@router.get("/forecast/overview")
def forecast_overview(medicine_id: Optional[str] = None, category: Optional[str] = None,
                      history_days: int = Query(60, ge=7, le=365), _user=Depends(pharmacist_only)):
    return svc.forecast_overview(medicine_id, category, history_days)


# ============================================================ inventory
@router.get("/inventory")
def inventory(stock_status: Optional[StockStatus] = None, medicine_id: Optional[str] = None,
             category: Optional[str] = None, search: Optional[str] = None, as_of: Optional[str] = DateQ,
             sort: Optional[str] = None, order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset,
             _user=Depends(pharmacist_only)):
    return inv_svc.inventory(stock_status.value if stock_status else None, medicine_id, category, search, as_of,
                             sort, order.value, limit, offset)


@router.get("/inventory/summary")
def inventory_summary(category: Optional[str] = None, as_of: Optional[str] = DateQ, _user=Depends(pharmacist_only)):
    return inv_svc.inventory_summary(as_of, category)


@router.get("/inventory/history")
def inventory_history(medicine_id: Optional[str] = None, category: Optional[str] = None,
                      date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, limit: int = Limit,
                      offset: int = Offset, _user=Depends(pharmacist_only)):
    return inv_svc.inventory_history(medicine_id, category, date_from, date_to, limit, offset)


@router.get("/inventory/status-trend")
def status_trend(medicine_id: Optional[str] = None, category: Optional[str] = None, date_from: Optional[str] = DateQ,
                 date_to: Optional[str] = DateQ, _user=Depends(pharmacist_only)):
    return inv_svc.status_trend(medicine_id, category, date_from, date_to)


@router.get("/inventory/batches")
def batches(status: Optional[ExpiryStatus] = None, medicine_id: Optional[str] = None, category: Optional[str] = None,
           search: Optional[str] = None, expiry_from: Optional[str] = DateQ, expiry_to: Optional[str] = DateQ,
           min_units: Optional[int] = Query(None, ge=0), as_of: Optional[str] = DateQ,
           near_expiry_days: Optional[int] = Query(None, ge=1, le=730), sort: Optional[str] = None,
           order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return inv_svc.batches(status.value if status else None, medicine_id, category, search, expiry_from, expiry_to,
                           min_units, as_of, near_expiry_days, sort, order.value, limit, offset)


@router.get("/inventory/reconciliation")
def reconciliation(medicine_id: Optional[str] = None, category: Optional[str] = None, as_of: Optional[str] = DateQ,
                   _user=Depends(pharmacist_only)):
    return inv_svc.reconciliation(medicine_id, category, as_of)


# ============================================================ expiry management
@router.get("/expiry")
def expiry(status: Optional[ExpiryStatus] = None, medicine_id: Optional[str] = None, category: Optional[str] = None,
          search: Optional[str] = None, expiry_from: Optional[str] = DateQ, expiry_to: Optional[str] = DateQ,
          min_units: Optional[int] = Query(None, ge=0), as_of: Optional[str] = DateQ,
          near_expiry_days: Optional[int] = Query(None, ge=1, le=730), sort: Optional[str] = None,
          order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return expiry_svc.expiry_list(status.value if status else None, medicine_id, category, search, expiry_from,
                                  expiry_to, min_units, as_of, near_expiry_days, sort, order.value, limit, offset)


@router.get("/expiry/summary")
def expiry_summary(medicine_id: Optional[str] = None, category: Optional[str] = None, as_of: Optional[str] = DateQ,
                   near_expiry_days: Optional[int] = Query(None, ge=1, le=730), _user=Depends(pharmacist_only)):
    return expiry_svc.expiry_summary(medicine_id, category, as_of, near_expiry_days)


@router.get("/expiry/alerts")
def expiry_alerts(severity: Optional[Severity] = None, medicine_id: Optional[str] = None,
                  category: Optional[str] = None, search: Optional[str] = None, date_from: Optional[str] = DateQ,
                  date_to: Optional[str] = DateQ, max_days: Optional[int] = None, sort: Optional[str] = None,
                  order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset,
                  _user=Depends(pharmacist_only)):
    return expiry_svc.expiry_alerts(severity.value if severity else None, medicine_id, category, search, date_from,
                                    date_to, max_days, sort, order.value, limit, offset)


# ============================================================ alerts
@router.get("/alerts")
def alerts(alert_type: Optional[str] = None, severity: Optional[Severity] = None, medicine_id: Optional[str] = None,
          category: Optional[str] = None, search: Optional[str] = None, date_from: Optional[str] = DateQ,
          date_to: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.asc,
          limit: int = Limit, offset: int = Offset, _user=Depends(pharmacist_only)):
    return alert_svc.alerts(alert_type, severity.value if severity else None, medicine_id, category, search,
                            date_from, date_to, sort, order.value, limit, offset)


# ============================================================ recommendations
@router.get("/recommendations")
def recommendations(recommendation_type: Optional[str] = None, severity: Optional[Severity] = None,
                    medicine_id: Optional[str] = None, category: Optional[str] = None, search: Optional[str] = None,
                    date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, sort: Optional[str] = None,
                    order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset,
                    _user=Depends(pharmacist_only)):
    return rec_svc.recommendations(recommendation_type, severity.value if severity else None, medicine_id, category,
                                   search, date_from, date_to, sort, order.value, limit, offset)


@router.get("/recommendations/forecast-based")
def forecast_based_recommendations(horizon_days: Optional[int] = Query(None, ge=1), medicine_id: Optional[str] = None,
                                   category: Optional[str] = None, _user=Depends(pharmacist_only)):
    return rec_svc.forecast_based(horizon_days, medicine_id, category)


# ============================================================ reports
@router.get("/reports/{report_type}")
def report(report_type: ReportType, medicine_id: Optional[str] = None, category: Optional[str] = None,
          date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, search: Optional[str] = None,
          alert_type: Optional[str] = None, severity: Optional[Severity] = None, as_of: Optional[str] = DateQ,
          near_expiry_days: Optional[int] = Query(None, ge=1, le=730), export: Optional[str] = None,
          _user=Depends(pharmacist_only)):
    fn = report_svc.REPORT_FUNCS[report_type.value]
    if report_type.value == "demand":
        result = fn(medicine_id, category, date_from, date_to, search)
    elif report_type.value == "forecast":
        result = fn(medicine_id, category, date_from, date_to)
    elif report_type.value == "inventory":
        result = fn(medicine_id, category, as_of)
    elif report_type.value == "expiry":
        result = fn(medicine_id, category, as_of, near_expiry_days)
    elif report_type.value == "alerts":
        result = fn(medicine_id, category, date_from, date_to, alert_type, severity.value if severity else None)
    else:
        result = fn(medicine_id, category, date_from, date_to)

    if export == "csv":
        csv_text = report_svc.as_csv(report_type.value, result["rows"])
        return PlainTextResponse(csv_text, media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="medicine_{report_type.value}_report.csv"'})
    if export and export != "csv":
        raise BadRequestError("export must be 'csv' if provided.")
    return result
