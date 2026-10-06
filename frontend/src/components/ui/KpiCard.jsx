import StatusBadge from "./StatusBadge";
import Skeleton from "./Skeleton";

export default function KpiCard({ icon: Icon, label, value, caption, status, statusLabel, loading, accent = "primary" }) {
  if (loading) {
    return (
      <div className="card stack gap-3" style={{ minHeight: 132 }}>
        <Skeleton width={32} height={32} radius={8} />
        <Skeleton width="60%" height={14} />
        <Skeleton width="40%" height={28} />
      </div>
    );
  }
  return (
    <div className="card stack gap-2 fade-in" style={{ minHeight: 132 }}>
      <div className="row-between">
        <div className={`kpi-icon kpi-icon-${accent}`}><Icon size={18} strokeWidth={2} /></div>
        {status && <StatusBadge status={status} label={statusLabel} />}
      </div>
      <div className="text-micro">{label}</div>
      <div className="metric-value">{value}</div>
      {caption && <div className="text-small">{caption}</div>}
    </div>
  );
}
