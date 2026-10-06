import { useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import FilterBar, { FilterField } from "../../components/ui/FilterBar";
import Section from "../../components/ui/Section";
import KpiCard from "../../components/ui/KpiCard";
import DataTable from "../../components/ui/DataTable";
import StatusBadge from "../../components/ui/StatusBadge";
import StatusDonut from "../../components/charts/StatusDonut";
import ErrorState from "../../components/ui/ErrorState";
import { AlertTriangle, XOctagon, CheckCircle2 } from "lucide-react";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";

const STATUSES = ["", "Expired", "Near Expiry", "Safe"];

export default function Expiry() {
  const [status, setStatus] = useState("Near Expiry");
  const { data: summary, loading: lSummary, error, refetch } = useApi(() => api.getExpirySummary({}), []);
  const { data: batches, loading } = useApi(() => api.getBatches({ status: status || undefined, limit: 100 }), [status]);

  const donutData = summary ? Object.entries(summary.by_status).map(([k, v]) => ({ status: k, count: v.batches })) : [];

  return (
    <div className="stack gap-6">
      <PageHeader title="Expiry Intelligence" subtitle="Batch-level expiry tracking derived from real dates." asOfDate={summary?.as_of_date} onRefresh={refetch} />

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <div className="grid grid-cols-3">
          <KpiCard icon={XOctagon} label="Expired" value={summary?.by_status?.Expired?.units} loading={lSummary} accent="danger" status="Expired"
            caption={summary && `${summary.by_status.Expired.batches} batches`} />
          <KpiCard icon={AlertTriangle} label="Near Expiry" value={summary?.units_approaching_expiry} loading={lSummary} accent="warning" status="Near Expiry"
            caption={summary && `within ${summary.near_expiry_days} days`} />
          <KpiCard icon={CheckCircle2} label="Safe" value={summary?.by_status?.Safe?.units} loading={lSummary} accent="success" status="Safe"
            caption={summary && `${summary.by_status.Safe.batches} batches`} />
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2">
          <Section title="Expiry Distribution"><StatusDonut data={donutData} loading={lSummary} /></Section>
          <Section title="Expiry Priority" subtitle="Near-expiry batches ordered by fewest days remaining.">
            <DataTable loading={lSummary} rows={(summary?.expiry_priority_batches?.items || []).slice(0, 6)}
              columns={[
                { key: "medicine_name", header: "Medicine" },
                { key: "days_remaining", header: "Days Left" },
                { key: "units_remaining", header: "Units" },
              ]} emptyMessage="No batches require priority attention." />
          </Section>
        </div>
      )}

      <FilterBar>
        <FilterField label="Expiry status">
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
          </select>
        </FilterField>
      </FilterBar>

      {!error && (
        <Section title="Batch Detail">
          <DataTable loading={loading} rows={batches?.items}
            columns={[
              { key: "medicine_name", header: "Medicine" }, { key: "batch_number", header: "Batch" },
              { key: "manufacturing_date", header: "Manufactured" }, { key: "expiry_date", header: "Expires" },
              { key: "days_remaining", header: "Days Left" }, { key: "units_remaining", header: "Units" },
              { key: "expiry_status", header: "Status", render: (r) => <StatusBadge status={r.expiry_status} /> },
            ]} />
        </Section>
      )}
    </div>
  );
}
