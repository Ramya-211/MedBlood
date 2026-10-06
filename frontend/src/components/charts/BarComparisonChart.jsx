import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";

const COLORS = ["#3366e6", "#d2454f", "#8b5cf6", "#34c77b"];

export default function BarComparisonChart({ data, bars, xKey, height = 280, loading, emptyMessage }) {
  if (loading) return <Skeleton height={height} radius={10} />;
  if (!data || data.length === 0) return <EmptyState title="No data" message={emptyMessage || "There is no data for the selected filters."} />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--color-border)" vertical={false} />
        <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: "var(--color-text-muted)" }} tickLine={false} axisLine={{ stroke: "var(--color-border)" }} />
        <YAxis tick={{ fontSize: 11, fill: "var(--color-text-muted)" }} tickLine={false} axisLine={false} width={44} />
        <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--color-border)", fontSize: 12 }} />
        {bars.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {bars.map((b, i) => (
          <Bar key={b.key} dataKey={b.key} name={b.name} fill={b.color || COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
