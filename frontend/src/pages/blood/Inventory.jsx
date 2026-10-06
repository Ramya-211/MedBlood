import { useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import FilterBar, { FilterField } from "../../components/ui/FilterBar";
import Section from "../../components/ui/Section";
import DataTable from "../../components/ui/DataTable";
import StatusBadge from "../../components/ui/StatusBadge";
import StatusDonut from "../../components/charts/StatusDonut";
import ErrorState from "../../components/ui/ErrorState";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/blood";

const STATUSES = ["", "Critical", "Low", "Normal", "Overstock"];
const GROUPS = ["A", "B", "AB", "O"];
const RH = { "": "", Positive: "+", Negative: "-" };

export default function BloodInventory() {
  const [status, setStatus] = useState("");
  const { data: summary, loading: lSummary } = useApi(() => api.getInventorySummary({}), []);
  const { data: inv, loading, error, refetch } = useApi(() => api.getInventory({ stock_status: status || undefined, limit: 100 }), [status]);

  const donutData = summary ? Object.entries(summary.by_status).map(([k, v]) => ({ status: k, count: v.segments })) : [];

  // Quick-scan grid of the 8 standard blood types, using the latest fetched inventory rows.
  const byType = {};
  (inv?.items || []).forEach((r) => {
    const key = `${r.blood_group}${r.rh_type === "Positive" ? "+" : "-"}`;
    byType[key] = byType[key] || { stock: 0, status: r.stock_status };
    byType[key].stock += r.closing_stock;
  });

  return (
    <div className="stack gap-6">
      <PageHeader title="Blood Inventory" subtitle="Live stock levels across all blood groups and components." asOfDate={inv?.as_of_date} onRefresh={refetch} />

      <Section title="Blood Group Status" subtitle="Quick scan across all 8 standard blood types.">
        <div className="blood-type-grid">
          {["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map((t) => (
            <div key={t} className="blood-type-cell">
              <span className="blood-type-label">{t}</span>
              <span className="text-h1">{byType[t]?.stock?.toLocaleString() ?? "—"}</span>
              {byType[t]?.status && <StatusBadge status={byType[t].status} />}
            </div>
          ))}
        </div>
      </Section>

      <div className="grid grid-cols-2">
        <Section title="Stock Status Overview"><StatusDonut data={donutData} loading={lSummary} /></Section>
        <Section title="Attention Needed" subtitle="Thresholds derived from days-of-cover.">
          {!lSummary && summary && (
            <div className="stack gap-3" style={{ justifyContent: "center", height: "100%" }}>
              <Row label="Low or Critical" value={summary.attention_needed.low_or_critical} tone="warning" />
              <Row label="Overstock" value={summary.attention_needed.overstock} tone="info" />
              <p className="text-micro" style={{ marginTop: 8 }}>{summary.stock_rule.definition}</p>
            </div>
          )}
        </Section>
      </div>

      <FilterBar>
        <FilterField label="Stock status">
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
          </select>
        </FilterField>
      </FilterBar>

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <Section title="Inventory Detail" subtitle={`${inv?.total ?? ""} segments matching this filter.`}>
          <DataTable loading={loading} rows={inv?.items}
            columns={[
              { key: "blood_group", header: "Group", render: (r) => `${r.blood_group}${r.rh_type === "Positive" ? "+" : "-"}` },
              { key: "blood_component", header: "Component" },
              { key: "closing_stock", header: "Stock", render: (r) => r.closing_stock.toLocaleString() },
              { key: "stock_status", header: "Status", render: (r) => <StatusBadge status={r.stock_status} /> },
              { key: "days_of_cover", header: "Days of Cover", render: (r) => r.days_of_cover != null ? r.days_of_cover.toFixed(1) : "—" },
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
      <span className="text-h2" style={{ color: tone === "warning" ? "var(--color-warning-600)" : "var(--color-info-600)" }}>{value}</span>
    </div>
  );
}
