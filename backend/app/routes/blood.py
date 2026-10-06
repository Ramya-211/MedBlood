"""
blood.py — Blood module routes. All endpoints require the BLOOD_STAFF role.
Mirrors routes/medicine.py structure and conventions exactly.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.dependencies import require_roles
from app.schemas.auth import Role
from app.schemas.blood import (BacktestGranularity, BloodComponent, BloodGroup, ExpiryStatus, Granularity,
                                GrowthPeriod, ReportType, RhType, Severity, SortOrder, StockStatus, VolumeTier)
from app.services import (blood_alert_service as alert_svc, blood_expiry_service as expiry_svc,
                          blood_inventory_service as inv_svc, blood_recommendation_service as rec_svc,
                          blood_report_service as report_svc, blood_service as svc)
from app.utils.errors import BadRequestError

router = APIRouter(prefix="/api/blood", tags=["blood"])
blood_staff_only = require_roles(Role.BLOOD_STAFF)

DateQ = Query(None, description="YYYY-MM-DD")
Limit = Query(25, ge=1, le=500)
Offset = Query(0, ge=0)
BG = Query(None, alias="blood_group")
RH = Query(None, alias="rh_type")
BC = Query(None, alias="blood_component")


def _v(x):
    return x.value if x is not None else None


# ============================================================ filters / dashboard
@router.get("/filters")
def filters(_user=Depends(blood_staff_only)):
    return svc.get_filters()


@router.get("/dashboard")
def dashboard(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
             blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
             date_to: Optional[str] = DateQ, _user=Depends(blood_staff_only)):
    return svc.dashboard(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to)


# ============================================================ demand analysis (DEMAND = units_requested)
@router.get("/demand")
def demand(granularity: Granularity, blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
          blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
          date_to: Optional[str] = DateQ, by_segment: bool = False, limit: int = Limit, offset: int = Offset,
          _user=Depends(blood_staff_only)):
    return svc.demand_series(granularity.value, _v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to,
                             by_segment, limit, offset)


@router.get("/demand/summary")
def demand_summary(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                   blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                   date_to: Optional[str] = DateQ, _user=Depends(blood_staff_only)):
    return svc.demand_summary(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to)


@router.get("/demand/rankings")
def demand_rankings(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                    blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                    date_to: Optional[str] = DateQ, limit: int = Query(5, ge=1, le=32), _user=Depends(blood_staff_only)):
    return svc.demand_rankings(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to, limit)


@router.get("/demand/variability")
def demand_variability(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                       blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                       date_to: Optional[str] = DateQ, _user=Depends(blood_staff_only)):
    return svc.demand_variability(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to)


@router.get("/demand/moving-average")
def moving_average(window: int = Query(7, description="7, 14, 30, 60 or 90"), blood_group: Optional[BloodGroup] = BG,
                   rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
                   date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, _user=Depends(blood_staff_only)):
    return svc.moving_average(window, _v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to)


@router.get("/demand/growth")
def demand_growth(period: GrowthPeriod = GrowthPeriod.week, blood_group: Optional[BloodGroup] = BG,
                  rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
                  _user=Depends(blood_staff_only)):
    return svc.demand_growth(period.value, _v(blood_group), _v(rh_type), _v(blood_component))


@router.get("/demand/trends")
def demand_trends(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                  blood_component: Optional[BloodComponent] = BC, _user=Depends(blood_staff_only)):
    return svc.demand_trends(_v(blood_group), _v(rh_type), _v(blood_component))


@router.get("/demand/seasonality")
def demand_seasonality(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                       blood_component: Optional[BloodComponent] = BC, _user=Depends(blood_staff_only)):
    return svc.demand_seasonality(_v(blood_group), _v(rh_type), _v(blood_component))


@router.get("/demand/anomalies")
def demand_anomalies(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                     blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                     date_to: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.desc,
                     limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return svc.demand_anomalies(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to, sort,
                                order.value, limit, offset)


@router.get("/demand/movement")
def demand_movement(blood_component: Optional[BloodComponent] = BC, sort: Optional[str] = None,
                    order: SortOrder = SortOrder.desc, _user=Depends(blood_staff_only)):
    return svc.demand_movement(_v(blood_component), sort, order.value)


# ============================================================ supply / collection (SUPPLY = donation_volume)
@router.get("/supply")
def supply(granularity: Granularity, blood_type: Optional[str] = None, date_from: Optional[str] = DateQ,
          date_to: Optional[str] = DateQ, by_type: bool = False, limit: int = Limit, offset: int = Offset,
          _user=Depends(blood_staff_only)):
    return svc.supply_series(granularity.value, blood_type, date_from, date_to, by_type, limit, offset)


@router.get("/supply/summary")
def supply_summary(blood_type: Optional[str] = None, date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ,
                   _user=Depends(blood_staff_only)):
    return svc.supply_summary(blood_type, date_from, date_to)


@router.get("/supply-vs-demand")
def supply_vs_demand(date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, _user=Depends(blood_staff_only)):
    return svc.supply_vs_demand(date_from, date_to)


# ============================================================ forecasting
@router.get("/forecast/models")
def forecast_models(_user=Depends(blood_staff_only)):
    return svc.model_comparison()


@router.get("/forecast/runs")
def forecast_runs(_user=Depends(blood_staff_only)):
    return svc.forecast_runs()


@router.get("/forecast/backtest")
def forecast_backtest(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                      blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                      date_to: Optional[str] = DateQ, _user=Depends(blood_staff_only)):
    return svc.backtest(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to)


@router.get("/forecast/actual-vs-predicted")
def actual_vs_predicted(granularity: BacktestGranularity = BacktestGranularity.daily, blood_group: Optional[BloodGroup] = BG,
                        rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
                        date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, limit: int = Limit,
                        offset: int = Offset, _user=Depends(blood_staff_only)):
    return svc.actual_vs_predicted(granularity.value, _v(blood_group), _v(rh_type), _v(blood_component), date_from,
                                   date_to, limit, offset)


@router.get("/forecast/backtest/rows")
def backtest_rows(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                  blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                  date_to: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.asc,
                  limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return svc.backtest_rows(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to, sort, order.value,
                             limit, offset)


@router.get("/forecast/future")
def future_forecast(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                    blood_component: Optional[BloodComponent] = BC, run_id: Optional[int] = None,
                    horizon: Optional[int] = Query(None, ge=1), limit: int = Limit, offset: int = Offset,
                    _user=Depends(blood_staff_only)):
    return svc.future_forecast(_v(blood_group), _v(rh_type), _v(blood_component), run_id, horizon, limit, offset)


@router.get("/forecast/overview")
def forecast_overview(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                      blood_component: Optional[BloodComponent] = BC, history_days: int = Query(60, ge=7, le=365),
                      _user=Depends(blood_staff_only)):
    return svc.forecast_overview(_v(blood_group), _v(rh_type), _v(blood_component), history_days)


# ============================================================ inventory (INVENTORY = closing_stock)
@router.get("/inventory")
def inventory(stock_status: Optional[StockStatus] = None, blood_group: Optional[BloodGroup] = BG,
             rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
             as_of: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.asc,
             limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return inv_svc.inventory(_v(stock_status), _v(blood_group), _v(rh_type), _v(blood_component), as_of, sort,
                             order.value, limit, offset)


@router.get("/inventory/summary")
def inventory_summary(blood_component: Optional[BloodComponent] = BC, as_of: Optional[str] = DateQ,
                      _user=Depends(blood_staff_only)):
    return inv_svc.inventory_summary(as_of, _v(blood_component))


@router.get("/inventory/history")
def inventory_history(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                      blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                      date_to: Optional[str] = DateQ, limit: int = Limit, offset: int = Offset,
                      _user=Depends(blood_staff_only)):
    return inv_svc.inventory_history(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to, limit, offset)


@router.get("/inventory/batches")
def batches(status: Optional[ExpiryStatus] = None, blood_group: Optional[BloodGroup] = BG,
           rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
           expiry_from: Optional[str] = DateQ, expiry_to: Optional[str] = DateQ,
           min_units: Optional[int] = Query(None, ge=0), as_of: Optional[str] = DateQ,
           near_expiry_days: Optional[int] = Query(None, ge=1, le=365), sort: Optional[str] = None,
           order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return inv_svc.batches(_v(status), _v(blood_group), _v(rh_type), _v(blood_component), expiry_from, expiry_to,
                           min_units, as_of, near_expiry_days, sort, order.value, limit, offset)


@router.get("/inventory/reconciliation")
def reconciliation(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                   blood_component: Optional[BloodComponent] = BC, as_of: Optional[str] = DateQ,
                   _user=Depends(blood_staff_only)):
    return inv_svc.reconciliation(_v(blood_group), _v(rh_type), _v(blood_component), as_of)


# ============================================================ expiry management
@router.get("/expiry")
def expiry(status: Optional[ExpiryStatus] = None, blood_group: Optional[BloodGroup] = BG,
          rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
          expiry_from: Optional[str] = DateQ, expiry_to: Optional[str] = DateQ,
          min_units: Optional[int] = Query(None, ge=0), as_of: Optional[str] = DateQ,
          near_expiry_days: Optional[int] = Query(None, ge=1, le=365), sort: Optional[str] = None,
          order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return expiry_svc.expiry_list(_v(status), _v(blood_group), _v(rh_type), _v(blood_component), expiry_from,
                                  expiry_to, min_units, as_of, near_expiry_days, sort, order.value, limit, offset)


@router.get("/expiry/summary")
def expiry_summary(blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                   blood_component: Optional[BloodComponent] = BC, as_of: Optional[str] = DateQ,
                   near_expiry_days: Optional[int] = Query(None, ge=1, le=365), _user=Depends(blood_staff_only)):
    return expiry_svc.expiry_summary(_v(blood_group), _v(rh_type), _v(blood_component), as_of, near_expiry_days)


# ============================================================ alerts
@router.get("/alerts")
def alerts(alert_type: Optional[str] = None, severity: Optional[Severity] = None, blood_group: Optional[BloodGroup] = BG,
          rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
          date_from: Optional[str] = DateQ, date_to: Optional[str] = DateQ, sort: Optional[str] = None,
          order: SortOrder = SortOrder.asc, limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return alert_svc.alerts(alert_type, _v(severity), _v(blood_group), _v(rh_type), _v(blood_component), date_from,
                            date_to, sort, order.value, limit, offset)


# ============================================================ recommendations
@router.get("/recommendations")
def recommendations(recommendation_type: Optional[str] = None, severity: Optional[Severity] = None,
                    blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
                    blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
                    date_to: Optional[str] = DateQ, sort: Optional[str] = None, order: SortOrder = SortOrder.asc,
                    limit: int = Limit, offset: int = Offset, _user=Depends(blood_staff_only)):
    return rec_svc.recommendations(recommendation_type, _v(severity), _v(blood_group), _v(rh_type), _v(blood_component),
                                   date_from, date_to, sort, order.value, limit, offset)


@router.get("/recommendations/forecast-based")
def forecast_based_recommendations(horizon_days: Optional[int] = Query(None, ge=1), blood_group: Optional[BloodGroup] = BG,
                                   rh_type: Optional[RhType] = RH, blood_component: Optional[BloodComponent] = BC,
                                   _user=Depends(blood_staff_only)):
    return rec_svc.forecast_based(horizon_days, _v(blood_group), _v(rh_type), _v(blood_component))


# ============================================================ reports
@router.get("/reports/{report_type}")
def report(report_type: ReportType, blood_group: Optional[BloodGroup] = BG, rh_type: Optional[RhType] = RH,
          blood_component: Optional[BloodComponent] = BC, date_from: Optional[str] = DateQ,
          date_to: Optional[str] = DateQ, alert_type: Optional[str] = None, severity: Optional[Severity] = None,
          as_of: Optional[str] = DateQ, near_expiry_days: Optional[int] = Query(None, ge=1, le=365),
          export: Optional[str] = None, _user=Depends(blood_staff_only)):
    fn = report_svc.REPORT_FUNCS[report_type.value]
    if report_type.value in ("demand", "forecast", "recommendations"):
        result = fn(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to)
    elif report_type.value == "inventory":
        result = fn(_v(blood_group), _v(rh_type), _v(blood_component), as_of)
    elif report_type.value == "expiry":
        result = fn(_v(blood_group), _v(rh_type), _v(blood_component), as_of, near_expiry_days)
    elif report_type.value == "alerts":
        result = fn(_v(blood_group), _v(rh_type), _v(blood_component), date_from, date_to, alert_type, _v(severity))
    else:  # supply_vs_demand
        result = fn(date_from, date_to)

    if export == "csv":
        csv_text = report_svc.as_csv(report_type.value, result["rows"])
        return PlainTextResponse(csv_text, media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="blood_{report_type.value}_report.csv"'})
    if export and export != "csv":
        raise BadRequestError("export must be 'csv' if provided.")
    return result
