import { Pill, Package, CalendarClock, BellRing, Sparkles } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import KpiCard from "../../components/ui/KpiCard";
import Section from "../../components/ui/Section";
import TrendChart from "../../components/charts/TrendChart";
import ErrorState from "../../components/ui/ErrorState";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";

export default function PharmacistDashboard() {
  const { data, loading, error, refetch } = useApi(() => api.getDashboard({}), []);
  const k = data?.kpis;

  const avp = data?.charts?.actual_vs_predicted;
  const avpData = avp ? mergeAvp(avp) : [];

  return (
    <div className="stack gap-6">
      <PageHeader title="Medicine Intelligence" subtitle="Monitor inventory, demand patterns, expiry risk and future requirements."
        asOfDate={data?.meta?.as_of_date} onRefresh={refetch} />

      {error && <ErrorState message={error} onRetry={refetch} />}
      {!error && (
        <div className="grid grid-cols-4">
          <KpiCard icon={Pill} label="Total Types of Medicines" value={k?.total_medicines} loading={loading} accent="primary" />
          <KpiCard icon={Package} label="Current Stock" value={k?.current_inventory?.units?.toLocaleString()} loading={loading} accent="info"
            caption={k && `${k.low_critical_stock.low + k.low_critical_stock.critical} medicines need attention`}
            status={k && (k.low_critical_stock.critical > 0 ? "Critical" : k.low_critical_stock.low > 0 ? "Low" : "Normal")} />
          <KpiCard icon={CalendarClock} label="Near Expiry" value={k?.near_expiry?.batches} loading={loading} accent="warning"
            caption={k && `${k.near_expiry.units} units across batches`} status={k && (k.near_expiry.expired_batches > 0 ? "Critical" : k.near_expiry.batches > 0 ? "Near Expiry" : "Safe")} />
          <KpiCard icon={BellRing} label="Active Alerts" value={k?.active_alerts?.total} loading={loading} accent="danger"
            status={k && (k.active_alerts.critical > 0 ? "Critical" : "Normal")} caption={k && `${k.active_alerts.critical} critical`} />
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2">
          <Section title="Weekly Demand Trend" subtitle="Total units requested per week.">
            <TrendChart loading={loading} data={data?.charts?.weekly_demand_trend?.items} 
            xKey="period_start"
              lines={[{ key: "units_requested", name: "Units Requested" }]} />
          </Section>
          <Section title="Predicted Demand" subtitle="Model-generated forecast." badge={<span className="badge badge-accent"><Sparkles size={10} /> AI Forecast</span>}>
            {k?.predicted_demand?.value != null ? (
              <div className="stack gap-2" style={{ justifyContent: "center", height: 240 }}>
                <span className="text-micro">Next {k.predicted_demand.horizon_days} days ({k.predicted_demand.model_name})</span>
                <span className="metric-value" style={{ fontSize: 42 }}>{Math.round(k.predicted_demand.value).toLocaleString()}</span>
                <span className="text-small">units requested, {k.predicted_demand.unit}</span>
              </div>
            ) : (
              <div className="text-small" style={{ padding: "60px 0", textAlign: "center" }}>{k?.predicted_demand?.message || "Loading..."}</div>
            )}
          </Section>
        </div>
      )}

      {!error && (
        <Section title="Actual vs Predicted Demand" subtitle="Historical backtest (solid) vs model-generated future forecast (dashed) — never the same series.">
          <TrendChart loading={loading} data={avpData} xKey="label" height={300}
            lines={[
  {
    key: "actual",
    name: "Actual (Backtest)",
    color: "#07beec",
  },
  {
    key: "predicted_backtest",
    name: "Predicted (Backtest)",
    color: "#1d2c61",
    dashed: true,
  },
  {
    key: "forecast",
    name: "Future Forecast",
    color: "#16A34A",
    dashed: true,
  },
]} />
        </Section>
      )}
    </div>
  );
}

function mergeAvp(avp) {
  const rows = [];
  (avp.historical_backtest?.items || []).forEach((it) => {
    rows.push({ label: it.period_start, actual: it.actual_demand, predicted_backtest: it.predicted_demand });
  });
  (avp.future_forecast?.items || []).forEach((it) => {
    rows.push({ label: it.forecast_date, forecast: it.predicted_demand });
  });
  return rows;
}
