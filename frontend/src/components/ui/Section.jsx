export default function Section({ title, subtitle, action, children, badge }) {
  return (
    <div className="card fade-in">
      <div className="card-title-row">
        <div className="stack gap-1">
          <div className="row gap-2"><h2 className="text-h2">{title}</h2>{badge}</div>
          {subtitle && <p className="text-small">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}
