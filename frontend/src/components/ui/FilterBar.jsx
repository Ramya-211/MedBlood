export default function FilterBar({ children }) {
  return <div className="card row wrap gap-3" style={{ padding: "var(--space-4)", marginBottom: "var(--space-5)" }}>{children}</div>;
}

export function FilterField({ label, children }) {
  return (
    <label className="stack gap-1" style={{ minWidth: 150 }}>
      <span className="text-micro">{label}</span>
      {children}
    </label>
  );
}
