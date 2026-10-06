import { Sparkles } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Section from "../../components/ui/Section";
import TrendChart from "../../components/charts/TrendChart";
import DataTable from "../../components/ui/DataTable";
import ErrorState from "../../components/ui/ErrorState";
import StatusBadge from "../../components/ui/StatusBadge";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/blood";

export default function BloodForecast() {
  const { data: models, loading: lModels, error, refetch } = useApi(() => api.getForecastModels(), []);
  const { data: overview, loading: lOverview } = useApi(() => api.getForecastOverview({ history_days: 60 }), []);

  const chartData = overview ? mergeSeries(overview) : [];

  return (
    <div className="stack gap-6">
      <PageHeader title="Demand Forecasting" subtitle="Compare historical model performance and projected blood demand." onRefresh={refetch} />

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <Section title="Model Performance" subtitle="Three primary algorithms compared on real test-set metrics (an internal baseline is used only for sanity-checking, not shown here).">
          <DataTable loading={lModels} rows={models?.items}
            columns={[
              { key: "model_name", header: "Model", render: (r) => (
                <span className="row gap-2">{r.model_name}{r.model_name === models?.selected_model && <span className="badge badge-accent">Selected</span>}</span>
              ) },
              { key: "mae", header: "MAE", render: (r) => r.mae.toFixed(3) },
              { key: "rmse", header: "RMSE", render: (r) => r.rmse.toFixed(3) },
              { key: "r2", header: "R²", render: (r) => r.r2.toFixed(3) },
            ]} />
        </Section>
      )}

      {!error && (
        <Section title="Historical vs Forecast Demand" subtitle="Observed history, historical backtest, and the future model-generated forecast — kept strictly separate."
          badge={<span className="badge badge-accent"><Sparkles size={10} /> AI Forecast</span>}>
          <TrendChart loading={lOverview} data={chartData} xKey="label" height={320}
            lines={[
              { key: "actual", name: "Observed Demand" },
              { key: "backtest_actual", name: "Backtest Actual", color: "#34c77b" },
              { key: "backtest_predicted", name: "Backtest Predicted", dashed: true, color: "#f6ad37" },
              { key: "forecast", name: "Future Forecast", color: "#8b5cf6", dashed: true },
            ]} />
          <div className="row gap-4 wrap" style={{ marginTop: 14 }}>
            <StatusBadge status="Backtest" label="Historical Backtest" />
            <StatusBadge status="Forecast" label="Future Forecast (model-generated)" />
          </div>
        </Section>
      )}
    </div>
  );
}

function mergeSeries(overview) {
  const rows = [];
  (overview.historical_actual?.series || []).forEach((s) => rows.push({ label: s.date, actual: s.units_requested }));
  (overview.historical_backtest?.series || []).forEach((s) => rows.push({ label: s.target_date, backtest_actual: s.actual_demand, backtest_predicted: s.predicted_demand }));
  (overview.future_forecast?.series || []).forEach((s) => rows.push({ label: s.date, forecast: s.predicted_demand }));
  return rows;
}
