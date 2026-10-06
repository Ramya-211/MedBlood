import { AlertOctagon } from "lucide-react";

export default function ErrorState({ title = "Unable to load data", message, onRetry }) {
  return (
    <div className="stack gap-3" style={{ alignItems: "center", textAlign: "center", padding: "36px 20px" }}>
      <AlertOctagon size={28} style={{ color: "var(--color-danger-500)" }} />
      <div className="text-h2">{title}</div>
      {message && <div className="text-small" style={{ maxWidth: 380 }}>{message}</div>}
      {onRetry && <button className="btn btn-secondary btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  );
}
