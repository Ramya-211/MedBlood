import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend } from "recharts";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";

const TONE_COLOR = {
  Normal: "#1d9f5f", Safe: "#1d9f5f", Low: "#e3900f", "Near Expiry": "#e3900f",
  Critical: "#e13a41", Expired: "#e13a41", Overstock: "#2f87dd",
};

export default function StatusDonut({ data, nameKey = "status", valueKey = "count", height = 220, loading }) {
  if (loading) return <Skeleton height={height} radius={10} />;
  const filtered = (data || []).filter((d) => d[valueKey] > 0);
  if (filtered.length === 0) return <EmptyState title="No data" message="Nothing to show for this status breakdown yet." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={filtered} dataKey={valueKey} nameKey={nameKey} innerRadius={56} outerRadius={82} paddingAngle={2}>
          {filtered.map((d, i) => <Cell key={i} fill={TONE_COLOR[d[nameKey]] || "#8990ac"} />)}
        </Pie>
        <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--color-border)", fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
