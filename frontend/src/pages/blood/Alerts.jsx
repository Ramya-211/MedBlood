import { useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import FilterBar, { FilterField } from "../../components/ui/FilterBar";
import Section from "../../components/ui/Section";
import StatusBadge from "../../components/ui/StatusBadge";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import Skeleton from "../../components/ui/Skeleton";
import { BellRing } from "lucide-react";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/blood";

const SEVERITIES = ["", "Critical", "Warning", "Info"];

export default function BloodAlerts() {
  const [severity, setSeverity] = useState("");
  const { data, loading, error, refetch } = useApi(() => api.getAlerts({ severity: severity || undefined, limit: 100 }), [severity]);

  const grouped = {};
  (data?.items || []).forEach((a) => { (grouped[a.severity] ||= []).push(a); });

  return (
    <div className="stack gap-6">
      <PageHeader title="Alert Center" subtitle="Current-state alerts generated from real inventory, expiry and demand conditions." onRefresh={refetch} />

      <FilterBar>
        <FilterField label="Severity">
          <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s || "All severities"}</option>)}
          </select>
        </FilterField>
      </FilterBar>

      {error && <ErrorState message={error} onRetry={refetch} />}
      {!error && data?.snapshot && <p className="text-micro">{data.snapshot.note}</p>}

      {!error && loading && <div className="stack gap-3">{[...Array(4)].map((_, i) => <Skeleton key={i} height={64} />)}</div>}

      {!error && !loading && (!data?.items?.length ? (
        <EmptyState icon={BellRing} title="No active alerts" message="Everything looks within normal parameters for this filter." />
      ) : (
        <div className="stack gap-5">
          {["Critical", "Warning", "Info"].filter((s) => grouped[s]?.length).map((sev) => (
            <Section key={sev} title={sev} badge={<span className="badge badge-neutral">{grouped[sev].length}</span>}>
              <div className="stack gap-3">
                {grouped[sev].map((a) => (
                  <div key={a.alert_id} className="alert-card">
                    <div className="row-between">
                      <div className="row gap-2"><StatusBadge status={a.severity} /><span className="text-small" style={{ fontWeight: 600 }}>{a.alert_type}</span></div>
                      <span className="text-micro">{a.date}</span>
                    </div>
                    <p className="text-small" style={{ marginTop: 6 }}>
                      {a.blood_group}{a.rh_type === "Positive" ? "+" : "-"} {a.blood_component}: {a.reason}
                    </p>
                  </div>
                ))}
              </div>
            </Section>
          ))}
        </div>
      ))}
    </div>
  );
}
