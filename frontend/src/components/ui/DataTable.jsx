import EmptyState from "./EmptyState";
import Skeleton from "./Skeleton";

export default function DataTable({ columns, rows, loading, emptyMessage = "No records match these filters." }) {
  if (loading) {
    return (
      <div className="stack gap-2">
        {[...Array(5)].map((_, i) => <Skeleton key={i} height={38} />)}
      </div>
    );
  }
  if (!rows || rows.length === 0) {
    return <EmptyState title="No data" message={emptyMessage} />;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.id ?? i}>
              {columns.map((c) => <td key={c.key}>{c.render ? c.render(row) : row[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
