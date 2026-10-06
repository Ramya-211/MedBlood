import { Sparkles } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Section from "../../components/ui/Section";
import TrendChart from "../../components/charts/TrendChart";
import DataTable from "../../components/ui/DataTable";
import ErrorState from "../../components/ui/ErrorState";
import StatusBadge from "../../components/ui/StatusBadge";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";

export default function Forecast() {
  const { data: models, loading: lModels, error, refetch } = useApi(() => api.getForecastModels(), []);
  const { data: overview, loading: lOverview } = useApi(() => api.getForecastOverview({ history_days: 60 }), []);

  const chartData = overview ? mergeSeries(overview) : [];

  return (
    <div className="stack gap-6">
      <PageHeader title="Demand Forecasting" subtitle="Compare historical model performance and projected future demand." onRefresh={refetch} />

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <Section title="Model Performance" subtitle="Evaluated on a chronological hold-out test set using real metrics.">
          <DataTable
  loading={lModels}
  rows={models?.items?.filter((m) => m.model_name !== "Baseline (naive lag-1)")}
            columns={[
              { key: "model_name", header: "Model", render: (r) => (
                <span className="row gap-2">{r.model_name}{r.model_name === models?.selected_model && <span className="badge badge-accent">Selected</span>}</span>
              ) },
              { key: "mae", header: "MAE", render: (r) => r.mae.toFixed(3) },
              { key: "rmse", header: "RMSE", render: (r) => r.rmse.toFixed(3) },
              { key: "r2", header: "R²", render: (r) => r.r2.toFixed(3) },
            ]} />
          {models && <p className="text-small" style={{ marginTop: 14 }}>{models.selection_rule}</p>}
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

      {!error && overview?.future_forecast?.available && (
        <Section title="Forecast Summary" subtitle={`Model: ${overview.future_forecast.run.model_name}, trained through ${overview.future_forecast.run.trained_through_date}.`}>
          <div className="grid grid-cols-3">
            <SummaryStat label="Trend Direction" value={overview.future_forecast.trend?.direction || "—"} />
            <SummaryStat label="Avg First 7 Days" value={overview.future_forecast.trend?.avg_first_7_days?.toFixed(1) ?? "—"} />
            <SummaryStat label="Avg Last 7 Days" value={overview.future_forecast.trend?.avg_last_7_days?.toFixed(1) ?? "—"} />
          </div>
        </Section>
      )}
    </div>
  );
}

function SummaryStat({ label, value }) {
  return (
    <div className="stack gap-1">
      <span className="text-micro">{label}</span>
      <span className="text-h1">{value}</span>
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
