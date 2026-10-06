import { Inbox } from "lucide-react";

export default function EmptyState({ icon: Icon = Inbox, title = "Nothing here yet", message, action }) {
  return (
    <div className="stack gap-2" style={{ alignItems: "center", textAlign: "center", padding: "40px 20px", color: "var(--color-text-secondary)" }}>
      <Icon size={30} strokeWidth={1.5} style={{ color: "var(--color-text-muted)" }} />
      <div className="text-h2" style={{ color: "var(--color-text-primary)" }}>{title}</div>
      {message && <div className="text-small" style={{ maxWidth: 360 }}>{message}</div>}
      {action}
    </div>
  );
}
