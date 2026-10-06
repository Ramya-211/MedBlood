import { useState } from "react";
import { TrendingUp, Zap } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import FilterBar, { FilterField } from "../../components/ui/FilterBar";
import Section from "../../components/ui/Section";
import KpiCard from "../../components/ui/KpiCard";
import TrendChart from "../../components/charts/TrendChart";
import DataTable from "../../components/ui/DataTable";
import ErrorState from "../../components/ui/ErrorState";
import StatusBadge from "../../components/ui/StatusBadge";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";
import { Activity, Package2 } from "lucide-react";

const GRANULARITIES = ["daily", "weekly", "monthly", "yearly"];

export default function Demand() {
  const [granularity, setGranularity] = useState("weekly");
  const [category, setCategory] = useState("");

  const { data: filters } = useApi(() => api.getFilters(), []);
  const { data: series, loading: lSeries, error: eSeries, refetch } = useApi(
    () => api.getDemand({ granularity, category: category || undefined }), [granularity, category]
  );
  const { data: summary, loading: lSummary } = useApi(() => api.getDemandSummary({ category: category || undefined }), [category]);
  const { data: trends, loading: lTrends } = useApi(() => api.getTrends({ category: category || undefined }), [category]);
  const { data: movement, loading: lMovement } = useApi(() => api.getMovement({ category: category || undefined }), [category]);
  const { data: anomalies, loading: lAnomalies } = useApi(() => api.getAnomalies({ category: category || undefined, limit: 8 }), [category]);

  return (
    <div className="stack gap-6">
      <PageHeader title="Medicine Demand" subtitle="Historical demand patterns across daily, weekly, monthly and yearly periods." onRefresh={refetch} />

      <FilterBar>
        <FilterField label="Granularity">
          <select className="select" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
            {GRANULARITIES.map((g) => <option key={g} value={g}>{g[0].toUpperCase() + g.slice(1)}</option>)}
          </select>
        </FilterField>
        <FilterField label="Category">
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {filters?.categories?.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </FilterField>
      </FilterBar>

      {eSeries && <ErrorState message={eSeries} onRetry={refetch} />}

      {!eSeries && (
        <div className="grid grid-cols-4">
          <KpiCard icon={Package2} label="Total Requested" value={summary?.kpis?.total_requested?.toLocaleString()} loading={lSummary} accent="primary" />
          <KpiCard icon={Activity} label="Avg Daily Demand" value={summary?.kpis?.average_daily_requested?.toFixed(1)} loading={lSummary} accent="info" />
          <KpiCard icon={TrendingUp} label="Increasing Trend" value={trends?.counts?.Increasing || 0} loading={lTrends} accent="success" />
          <KpiCard icon={Zap} label="Anomalies Detected" value={anomalies?.total} loading={lAnomalies} accent="warning" />
        </div>
      )}

      {!eSeries && (
        <Section title="Demand Trend" subtitle={`Units requested per ${granularity} period.`}>
          <TrendChart loading={lSeries} data={series?.items} xKey="period_start" lines={[{ key: "units_requested", name: "Units Requested" }]} />
        </Section>
      )}

      {!eSeries && (
        <div className="grid grid-cols-2">
          <Section title="Demand Trend by Medicine" subtitle="Increasing, decreasing or stable over the full history.">
            <DataTable loading={lTrends} rows={(trends?.items || []).slice(0, 8)}
              columns={[
                { key: "medicine_name", header: "Medicine" },
                { key: "trend_direction", header: "Trend", render: (r) => <StatusBadge status={r.trend_direction} /> },
                { key: "growth_rate_7d", header: "7d Growth", render: (r) => r.growth_rate_7d != null ? `${(r.growth_rate_7d * 100).toFixed(1)}%` : "—" },
              ]} />
          </Section>
          <Section title="Movement Classification" subtitle="Fast / medium / slow moving medicines (full-history ranking).">
            <DataTable loading={lMovement} rows={(movement?.items || []).slice(0, 8)}
              columns={[
                { key: "medicine_name", header: "Medicine" },
                { key: "volume_tier", header: "Tier", render: (r) => <span className="badge badge-neutral">{r.volume_tier}</span> },
                { key: "total_units_dispensed", header: "Total Dispensed", render: (r) => r.total_units_dispensed.toLocaleString() },
              ]} />
          </Section>
        </div>
      )}

      {!eSeries && (
        <Section title="Demand Anomalies" subtitle="Days where demand deviated significantly from the 30-day trend.">
          <DataTable loading={lAnomalies} rows={anomalies?.items}
            columns={[
              { key: "date", header: "Date" },
              { key: "medicine_name", header: "Medicine" },
              { key: "actual_demand", header: "Actual" },
              { key: "expected_demand", header: "Expected", render: (r) => r.expected_demand?.toFixed(1) },
              { key: "anomaly_type", header: "Type", render: (r) => <StatusBadge status={r.anomaly_type === "Demand Spike" ? "Warning" : "Info"} label={r.anomaly_type} /> },
            ]} emptyMessage="No demand anomalies detected for this filter." />
        </Section>
      )}
    </div>
  );
}
