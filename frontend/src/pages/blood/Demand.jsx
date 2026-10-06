import { useState } from "react";
import { TrendingUp, Zap, Droplet, ArrowLeftRight } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import FilterBar, { FilterField } from "../../components/ui/FilterBar";
import Section from "../../components/ui/Section";
import KpiCard from "../../components/ui/KpiCard";
import TrendChart from "../../components/charts/TrendChart";
import DataTable from "../../components/ui/DataTable";
import ErrorState from "../../components/ui/ErrorState";
import StatusBadge from "../../components/ui/StatusBadge";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/blood";

const GRANULARITIES = ["daily", "weekly", "monthly", "yearly"];

export default function BloodDemand() {
  const [granularity, setGranularity] = useState("weekly");
  const [bloodGroup, setBloodGroup] = useState("");

  const { data: filters } = useApi(() => api.getFilters(), []);
  const { data: series, loading: lSeries, error, refetch } = useApi(
    () => api.getDemand({ granularity, blood_group: bloodGroup || undefined }), [granularity, bloodGroup]
  );
  const { data: summary, loading: lSummary } = useApi(() => api.getDemandSummary({ blood_group: bloodGroup || undefined }), [bloodGroup]);
  const { data: svd, loading: lSvd } = useApi(() => api.getSupplyVsDemand({}), []);
  const { data: anomalies, loading: lAnomalies } = useApi(() => api.getAnomalies({ blood_group: bloodGroup || undefined, limit: 8 }), [bloodGroup]);

  return (
    <div className="stack gap-6">
      <PageHeader title="Blood Demand" subtitle="Patient-requested blood units — never confused with donation volume." onRefresh={refetch} />

      <FilterBar>
        <FilterField label="Granularity">
          <select className="select" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
            {GRANULARITIES.map((g) => <option key={g} value={g}>{g[0].toUpperCase() + g.slice(1)}</option>)}
          </select>
        </FilterField>
        <FilterField label="Blood group">
          <select className="select" value={bloodGroup} onChange={(e) => setBloodGroup(e.target.value)}>
            <option value="">All groups</option>
            {filters?.blood_groups?.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </FilterField>
      </FilterBar>

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <div className="grid grid-cols-4">
          <KpiCard icon={Droplet} label="Total Requested" value={summary?.kpis?.total_requested?.toLocaleString()} loading={lSummary} accent="blood" />
          <KpiCard icon={TrendingUp} label="Avg Daily Demand" value={summary?.kpis?.average_daily_requested?.toFixed(1)} loading={lSummary} accent="info" />
          <KpiCard icon={ArrowLeftRight} label="Supply vs Demand" value={svd?.items?.length} loading={lSvd} accent="primary" caption="Blood types compared" />
          <KpiCard icon={Zap} label="Anomalies Detected" value={anomalies?.total} loading={lAnomalies} accent="warning" />
        </div>
      )}

      {!error && (
        <Section title="Demand Trend" subtitle={`Units requested per ${granularity} period.`}>
          <TrendChart loading={lSeries} data={series?.items} xKey="period_start" lines={[{ key: "units_requested", name: "Units Requested" }]} />
        </Section>
      )}

      {!error && (
        <Section title="Supply vs Demand" subtitle="Donation volume vs. patient-requested units, by blood type.">
          <DataTable loading={lSvd} rows={svd?.items}
            columns={[
              { key: "blood_type", header: "Blood Type" },
              { key: "total_demand_requested", header: "Requested (Demand)", render: (r) => r.total_demand_requested?.toLocaleString() ?? "—" },
              { key: "total_supply_donation_volume", header: "Donated (Supply)", render: (r) => r.total_supply_donation_volume?.toLocaleString() ?? "—" },
            ]} />
          {svd?.limitation && <p className="text-micro" style={{ marginTop: 10 }}>{svd.limitation}</p>}
        </Section>
      )}

      {!error && (
        <Section title="Demand Anomalies" subtitle="Days where demand deviated significantly from the 30-day trend.">
          <DataTable loading={lAnomalies} rows={anomalies?.items}
            columns={[
              { key: "date", header: "Date" },
              { key: "blood_group", header: "Group", render: (r) => `${r.blood_group}${r.rh_type === "Positive" ? "+" : "-"}` },
              { key: "blood_component", header: "Component" },
              { key: "actual_demand", header: "Actual" },
              { key: "anomaly_type", header: "Type", render: (r) => <StatusBadge status={r.anomaly_type === "Demand Spike" ? "Warning" : "Info"} label={r.anomaly_type} /> },
            ]} emptyMessage="No demand anomalies detected for this filter." />
        </Section>
      )}
    </div>
  );
}
