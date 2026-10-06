import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";

const COLORS = ["#3366e6", "#8b5cf6", "#34c77b", "#f6ad37"];

export default function TrendChart({ data, lines, xKey, height = 280, loading, unit = "units", emptyMessage }) {
  if (loading) return <Skeleton height={height} radius={10} />;
  if (!data || data.length === 0) return <EmptyState title="No trend data" message={emptyMessage || "There is no data for the selected filters."} />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--color-border)" vertical={false} />
        <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: "var(--color-text-muted)" }} tickLine={false} axisLine={{ stroke: "var(--color-border)" }} />
        <YAxis tick={{ fontSize: 11, fill: "var(--color-text-muted)" }} tickLine={false} axisLine={false} width={44}
          label={{ value: unit, angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--color-text-muted)" }} />
        <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--color-border)", fontSize: 12 }} />
        {lines.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {lines.map((l, i) => (
          <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color || COLORS[i % COLORS.length]}
            strokeWidth={2} dot={false} strokeDasharray={l.dashed ? "5 4" : undefined} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
