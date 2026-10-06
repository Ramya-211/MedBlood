import { CheckCircle2, AlertTriangle, XCircle, Info, Sparkles } from "lucide-react";

// Single source of truth for status -> semantic color across the whole app.
// GREEN = healthy/safe, AMBER = warning/near-expiry/low, RED = critical/expired/shortage,
// BLUE = informational, PURPLE = AI/forecast related.
const MAP = {
  Normal: ["success", CheckCircle2], Safe: ["success", CheckCircle2], Increasing: ["success", CheckCircle2],
  Low: ["warning", AlertTriangle], "Near Expiry": ["warning", AlertTriangle], Warning: ["warning", AlertTriangle],
  Stable: ["info", Info], Overstock: ["info", Info],
  Critical: ["danger", XCircle], Expired: ["danger", XCircle], Decreasing: ["danger", XCircle],
  Info: ["info", Info],
  Forecast: ["accent", Sparkles], Backtest: ["accent", Sparkles],
};

export default function StatusBadge({ status, label }) {
  const [tone, Icon] = MAP[status] || ["neutral", Info];
  return (
    <span className={`badge badge-${tone}`}>
      <Icon size={11} strokeWidth={2.5} />
      {label || status}
    </span>
  );
}
