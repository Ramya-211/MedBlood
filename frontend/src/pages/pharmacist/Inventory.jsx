import { useState } from "react";
import { Search } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import FilterBar, { FilterField } from "../../components/ui/FilterBar";
import Section from "../../components/ui/Section";
import DataTable from "../../components/ui/DataTable";
import StatusBadge from "../../components/ui/StatusBadge";
import StatusDonut from "../../components/charts/StatusDonut";
import ErrorState from "../../components/ui/ErrorState";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";

const STATUSES = ["", "Critical", "Low", "Normal", "Overstock"];

export default function Inventory() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  const { data: summary, loading: lSummary } = useApi(() => api.getInventorySummary({}), []);
  const { data: inv, loading, error, refetch } = useApi(
    () => api.getInventory({ stock_status: status || undefined, search: search || undefined, limit: 100 }), [status, search]
  );

  const donutData = summary ? Object.entries(summary.by_status).map(([k, v]) => ({ status: k, count: v.medicines })) : [];

  return (
    <div className="stack gap-6">
      <PageHeader title="Medicine Inventory" subtitle="Live stock levels, batch status and replenishment risk." asOfDate={inv?.as_of_date} onRefresh={refetch} />

      <div className="grid grid-cols-2">
        <Section title="Stock Status Overview">
          <StatusDonut data={donutData} loading={lSummary} />
        </Section>
        <Section title="Attention Needed" subtitle="Thresholds derived from days-of-cover (closing stock / avg daily issuance).">
          {!lSummary && summary && (
            <div className="stack gap-3" style={{ justifyContent: "center", height: "100%" }}>
              <Row label="Low or Critical stock" value={summary.attention_needed.low_or_critical} tone="warning" />
              <Row label="Overstock" value={summary.attention_needed.overstock} tone="info" />
              <Row label="Total medicines tracked" value={summary.total_medicines} />
              <p className="text-micro" style={{ marginTop: 8 }}>{summary.stock_rule.definition}</p>
            </div>
          )}
        </Section>
      </div>

      <FilterBar>
        <FilterField label="Search">
          <div className="row gap-2"><Search size={14} style={{ color: "var(--color-text-muted)" }} />
            <input className="input" placeholder="Medicine name or ID" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </FilterField>
        <FilterField label="Stock status">
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
          </select>
        </FilterField>
      </FilterBar>

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <Section title="Inventory" subtitle={`${inv?.total ?? ""} medicines matching this filter.`}>
          <DataTable loading={loading} rows={inv?.items}
            columns={[
              { key: "medicine_name", header: "Medicine" }, { key: "category", header: "Category" },
              { key: "closing_stock", header: "Stock", render: (r) => r.closing_stock.toLocaleString() },
              { key: "stock_status", header: "Status", render: (r) => <StatusBadge status={r.stock_status} /> },
              { key: "days_of_cover", header: "Days of Cover", render: (r) => r.days_of_cover != null ? r.days_of_cover.toFixed(1) : "—" },
              { key: "units_issued", header: "Issued (day)" },
            ]} />
        </Section>
      )}
    </div>
  );
}

function Row({ label, value, tone }) {
  return (
    <div className="row-between">
      <span className="text-small">{label}</span>
      <span className="text-h2" style={{ color: tone === "warning" ? "var(--color-warning-600)" : tone === "info" ? "var(--color-info-600)" : "var(--color-text-primary)" }}>{value}</span>
    </div>
  );
}
