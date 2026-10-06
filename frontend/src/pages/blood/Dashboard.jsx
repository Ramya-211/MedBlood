import { Droplet, Package, CalendarClock, BellRing, Sparkles, ArrowLeftRight } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import KpiCard from "../../components/ui/KpiCard";
import Section from "../../components/ui/Section";
import TrendChart from "../../components/charts/TrendChart";
import ErrorState from "../../components/ui/ErrorState";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/blood";

export default function BloodDashboard() {
  const { data, loading, error, refetch } = useApi(() => api.getDashboard({}), []);
  const k = data?.kpis;
  const avp = data?.charts?.actual_vs_predicted;
  const avpData = avp ? mergeAvp(avp) : [];

  return (
    <div className="stack gap-6">
      <PageHeader title="Blood Resource Intelligence" subtitle="Monitor blood demand, supply, inventory and expiry risk across all groups."
        asOfDate={data?.meta?.as_of_date} onRefresh={refetch} />

      {error && <ErrorState message={error} onRetry={refetch} />}
      {!error && (
        <div className="grid grid-cols-4">
          <KpiCard icon={Droplet} label="Total Available" value={k?.total_available_units?.value?.toLocaleString()} loading={loading} accent="blood" />
          <KpiCard icon={ArrowLeftRight} label="Supply − Demand" value={k?.supply_minus_demand?.value?.toLocaleString()} loading={loading} accent="info"
            caption="Over the selected range" />
          <KpiCard icon={Package} label="Low-Stock Groups" value={k?.low_stock_segments?.count} loading={loading} accent="warning"
            status={k && (k.low_stock_segments.count > 0 ? "Low" : "Normal")} />
          <KpiCard icon={CalendarClock} label="Near Expiry" value={k?.near_expiry?.batches} loading={loading} accent="warning"
            status={k && (k.near_expiry.expired_batches > 0 ? "Critical" : k.near_expiry.batches > 0 ? "Near Expiry" : "Safe")}
            caption={k && `${k.near_expiry.units} units`} />
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2">
          <Section title="Weekly Blood Demand" subtitle="Units requested per week (patient demand, not donations).">
            <TrendChart loading={loading} data={data?.charts?.weekly_demand_trend?.items} xKey="period_start"
              lines={[{ key: "units_requested", name: "Units Requested" }]} />
          </Section>
          <Section title="Predicted Demand" subtitle="Model-generated forecast." badge={<span className="badge badge-accent"><Sparkles size={10} /> AI Forecast</span>}>
            {k?.predicted_demand?.value != null ? (
              <div className="stack gap-2" style={{ justifyContent: "center", height: 240 }}>
                <span className="text-micro">Next {k.predicted_demand.horizon_days} days ({k.predicted_demand.model_name})</span>
                <span className="metric-value" style={{ fontSize: 42 }}>{Math.round(k.predicted_demand.value).toLocaleString()}</span>
                <span className="text-small">units requested</span>
              </div>
            ) : (
              <div className="text-small" style={{ padding: "60px 0", textAlign: "center" }}>{k?.predicted_demand?.message || "Loading..."}</div>
            )}
          </Section>
        </div>
      )}

      {!error && (
        <Section title="Actual vs Predicted Demand" subtitle="Historical backtest vs model-generated future forecast — never the same series.">
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
  (avp.historical_backtest?.items || []).forEach((it) => rows.push({ label: it.period_start, actual: it.actual_demand, predicted_backtest: it.predicted_demand }));
  (avp.future_forecast?.items || []).forEach((it) => rows.push({ label: it.forecast_date, forecast: it.predicted_demand }));
  return rows;
}
