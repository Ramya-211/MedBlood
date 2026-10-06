import { useState } from "react";
import { TrendingUp, Sparkles, Package, CalendarClock, BellRing, Lightbulb, Download } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Section from "../../components/ui/Section";
import DataTable from "../../components/ui/DataTable";
import ErrorState from "../../components/ui/ErrorState";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";

const REPORTS = [
  { type: "demand", label: "Demand Report", icon: TrendingUp, desc: "Analyze historical demand patterns." },
  { type: "forecast", label: "Forecast Report", icon: Sparkles, desc: "Review projected demand and model accuracy." },
  { type: "inventory", label: "Inventory Report", icon: Package, desc: "Review current inventory and stock status." },
  { type: "expiry", label: "Expiry Report", icon: CalendarClock, desc: "Identify expiry risks by batch." },
  { type: "alerts", label: "Alert Report", icon: BellRing, desc: "Active alerts across the system." },
  { type: "recommendations", label: "Recommendation Report", icon: Lightbulb, desc: "Current-state recommendations." },
];

export default function Reports() {
  const [active, setActive] = useState(null);
  const { data, loading, error, refetch } = useApi(() => (active ? api.getReport(active, {}) : Promise.resolve(null)), [active]);

  return (
    <div className="stack gap-6">
      <PageHeader title="Report Center" subtitle="Dedicated reports with summaries, tables and CSV export." />

      <div className="grid grid-cols-3">
        {REPORTS.map((r) => (
          <div key={r.type} className={`card stack gap-2 clickable ${active === r.type ? "report-card-active" : ""}`} onClick={() => setActive(r.type)}>
            <div className="kpi-icon kpi-icon-primary"><r.icon size={18} /></div>
            <div className="text-h2" style={{ fontSize: 15 }}>{r.label}</div>
            <p className="text-small">{r.desc}</p>
            <div className="row gap-2" style={{ marginTop: 4 }}>
              <button className="btn btn-secondary btn-sm" onClick={(e) => { e.stopPropagation(); setActive(r.type); }}>View Report</button>
             <button
  className="btn btn-ghost btn-sm"
  onClick={(e) => {
    e.stopPropagation();
    api.downloadReportCsv(r.type, {});
  }}
>
  <Download size={13} /> Export
</button>
            </div>
          </div>
        ))}
      </div>

      {active && error && <ErrorState message={error} onRetry={refetch} />}
      {active && !error && (
        <Section
  title={REPORTS.find((r) => r.type === active).label}
  subtitle={`${data?.row_count ?? ""} rows.`}
  action={
    <button
      className="btn btn-secondary btn-sm"
      onClick={() => api.downloadReportCsv(active, {})}
    >
      <Download size={13} /> Export CSV
    </button>
  }
>
          {data?.summary && (
            <div className="text-small" style={{ marginBottom: 14, color: "var(--color-text-secondary)" }}>
              {Object.entries(data.summary).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ")}
            </div>
          )}
          <DataTable loading={loading} rows={data?.rows?.slice(0, 50)}
            columns={(data?.columns || []).map((c) => ({ key: c, header: c.replace(/_/g, " ") }))} />
        </Section>
      )}
    </div>
  );
}
