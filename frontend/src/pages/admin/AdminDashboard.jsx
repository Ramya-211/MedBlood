import { Users, Pill, Droplet, BellRing, ShieldCheck, Activity } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import KpiCard from "../../components/ui/KpiCard";
import Section from "../../components/ui/Section";
import StatusBadge from "../../components/ui/StatusBadge";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import Skeleton from "../../components/ui/Skeleton";
import { useApi } from "../../hooks/useApi";
import * as adminApi from "../../api/admin";

export default function AdminDashboard() {
  const { data, loading, error, refetch } = useApi(() => adminApi.getDashboard(), []);

  return (
    <div className="stack gap-6">
      <PageHeader title="System Overview" subtitle="Monitor users, medicine and blood operations, and active alerts across the platform." onRefresh={refetch} />

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!error && (
        <div className="grid grid-cols-4">
          <KpiCard icon={Users} label="Total Users" value={loading ? "" : data?.users.total} loading={loading} accent="primary"
            caption={!loading && `${data?.users.by_role.PHARMACIST?.total || 0} pharmacists, ${data?.users.by_role.BLOOD_STAFF?.total || 0} blood staff`} />
          <KpiCard icon={Pill} label="Total Medicines" value={loading ? "" : data?.medicine.total_medicines} loading={loading} accent="info"
            caption={!loading && `${data?.medicine.total_units.toLocaleString()} units in stock`} />
          <KpiCard icon={Droplet} label="Blood Units Available" value={loading ? "" : data?.blood.total_units.toLocaleString()} loading={loading} accent="blood"
            caption={!loading && `as of ${data?.blood.as_of_date}`} />
          <KpiCard icon={BellRing} label="Active Alerts" value={loading ? "" : data?.active_alerts_total} loading={loading} accent="warning"
            status={!loading && data?.active_alerts_total > 0 ? "Warning" : "Normal"}
            caption={!loading && `${data?.medicine.active_alerts} medicine, ${data?.blood.active_alerts} blood`} />
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2">
          <Section title="Medicine Overview" subtitle="Snapshot as of the latest inventory date.">
            {loading ? <Skeleton height={120} /> : (
              <div className="stack gap-3">
                <Row label="Total medicines" value={data.medicine.total_medicines} />
                <Row label="Units in stock" value={data.medicine.total_units.toLocaleString()} />
                <Row label="Low / Critical stock medicines" value={data.medicine.low_or_critical_medicines} warn={data.medicine.low_or_critical_medicines > 0} />
                <Row label="Active alerts" value={data.medicine.active_alerts} warn={data.medicine.active_alerts > 0} />
              </div>
            )}
          </Section>
          <Section title="Blood Overview" subtitle="Snapshot as of the latest inventory date.">
            {loading ? <Skeleton height={120} /> : (
              <div className="stack gap-3">
                <Row label="Units available" value={data.blood.total_units.toLocaleString()} />
                <Row label="Active alerts" value={data.blood.active_alerts} warn={data.blood.active_alerts > 0} />
                <Row label="Data as of" value={data.blood.as_of_date} />
              </div>
            )}
          </Section>
        </div>
      )}

      {!error && (
        <Section title="Recent Alerts" subtitle="Highest-severity alerts across Medicine and Blood.">
          {loading ? <Skeleton height={160} /> : !data.recent_alerts.length ? (
            <EmptyState title="No active alerts" message="The system has no active alerts right now." />
          ) : (
            <div className="stack gap-3">
              {data.recent_alerts.map((a, i) => (
                <div key={i} className="row-between" style={{ padding: "10px 0", borderBottom: i < data.recent_alerts.length - 1 ? "1px solid var(--color-border)" : "none" }}>
                  <div className="row gap-3">
                    <div className={`kpi-icon kpi-icon-${a.domain === "blood" ? "blood" : "primary"}`}>
                      {a.domain === "blood" ? <Droplet size={16} /> : <Pill size={16} />}
                    </div>
                    <div className="stack gap-0">
                      <span className="text-small" style={{ fontWeight: 600 }}>{a.alert_type}</span>
                      <span className="text-micro">{a.message}</span>
                    </div>
                  </div>
                  <StatusBadge status={a.severity} />
                </div>
              ))}
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

function Row({ label, value, warn }) {
  return (
    <div className="row-between">
      <span className="text-small">{label}</span>
      <span className="text-small" style={{ fontWeight: 600, color: warn ? "var(--color-warning-600)" : "var(--color-text-primary)" }}>{value}</span>
    </div>
  );
}
