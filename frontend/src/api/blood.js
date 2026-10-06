import client from "./client";

const g = (path, params) => client.get(`/api/blood${path}`, { params }).then((r) => r.data);

export const getFilters = () => g("/filters");
export const getDashboard = (params) => g("/dashboard", params);
export const getDemand = (params) => g("/demand", params);
export const getDemandSummary = (params) => g("/demand/summary", params);
export const getDemandRankings = (params) => g("/demand/rankings", params);
export const getDemandVariability = (params) => g("/demand/variability", params);
export const getMovingAverage = (params) => g("/demand/moving-average", params);
export const getGrowth = (params) => g("/demand/growth", params);
export const getTrends = (params) => g("/demand/trends", params);
export const getSeasonality = (params) => g("/demand/seasonality", params);
export const getAnomalies = (params) => g("/demand/anomalies", params);
export const getMovement = (params) => g("/demand/movement", params);

export const getSupply = (params) => g("/supply", params);
export const getSupplySummary = (params) => g("/supply/summary", params);
export const getSupplyVsDemand = (params) => g("/supply-vs-demand", params);

export const getForecastModels = () => g("/forecast/models");
export const getForecastRuns = () => g("/forecast/runs");
export const getBacktest = (params) => g("/forecast/backtest", params);
export const getActualVsPredicted = (params) => g("/forecast/actual-vs-predicted", params);
export const getFutureForecast = (params) => g("/forecast/future", params);
export const getForecastOverview = (params) => g("/forecast/overview", params);

export const getInventory = (params) => g("/inventory", params);
export const getInventorySummary = (params) => g("/inventory/summary", params);
export const getBatches = (params) => g("/inventory/batches", params);
export const getReconciliation = (params) => g("/inventory/reconciliation", params);

export const getExpiry = (params) => g("/expiry", params);
export const getExpirySummary = (params) => g("/expiry/summary", params);

export const getAlerts = (params) => g("/alerts", params);
export const getRecommendations = (params) => g("/recommendations", params);
export const getForecastRecommendations = (params) => g("/recommendations/forecast-based", params);

export const getReport = (type, params) => g(`/reports/${type}`, params);
export const downloadReportCsv = async (type, params = {}) => {
  const response = await client.get(`/api/blood/reports/${type}`, {
    params: { ...params, export: "csv" },
    responseType: "blob",
  });

  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");

  link.href = url;
  link.download = `${type}_report.csv`;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(url);
};