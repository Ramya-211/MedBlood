import { RefreshCw } from "lucide-react";

export default function PageHeader({ title, subtitle, asOfDate, onRefresh, actions }) {
  return (
    <div className="row-between wrap gap-3" style={{ marginBottom: "var(--space-6)" }}>
      <div className="stack gap-1">
        <h1 className="text-display">{title}</h1>
        {subtitle && <p className="text-secondary">{subtitle}</p>}
      </div>
      <div className="row gap-2">
        {asOfDate && <span className="badge badge-neutral">Data as of {asOfDate}</span>}
        {actions}
        {onRefresh && (
          <button className="btn btn-secondary btn-sm" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>
        )}
      </div>
    </div>
  );
}
