import { useState } from "react";
import { Sparkles } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import StatusBadge from "../../components/ui/StatusBadge";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import Skeleton from "../../components/ui/Skeleton";
import { useApi } from "../../hooks/useApi";
import * as api from "../../api/medicine";

export default function Recommendations() {
  const [tab, setTab] = useState("supplied");
  const { data: supplied, loading: lSupplied, error: eSupplied, refetch: rSupplied } = useApi(() => api.getRecommendations({ limit: 100 }), []);
  const { data: forecastBased, loading: lForecast, error: eForecast, refetch: rForecast } = useApi(() => api.getForecastRecommendations({}), []);

  const loading = tab === "supplied" ? lSupplied : lForecast;
  const error = tab === "supplied" ? eSupplied : eForecast;
  const refetch = tab === "supplied" ? rSupplied : rForecast;
  const items = tab === "supplied" ? supplied?.items : forecastBased?.items;

  return (
    <div className="stack gap-6">
      <PageHeader title="Recommendations" subtitle="Every recommendation explains the real data behind it." onRefresh={refetch} />

      <div className="row gap-2">
        <button className={`btn ${tab === "supplied" ? "btn-primary" : "btn-secondary"} btn-sm`} onClick={() => setTab("supplied")}>Current-State</button>
        <button className={`btn ${tab === "forecast" ? "btn-primary" : "btn-secondary"} btn-sm`} onClick={() => setTab("forecast")}>
          <Sparkles size={13} /> Forecast-Based
        </button>
      </div>

      {error && <ErrorState message={error} onRetry={refetch} />}
      {!error && tab === "forecast" && forecastBased && !forecastBased.available && (
        <EmptyState title="No forecast available" message={forecastBased.message} />
      )}

      {!error && loading && <div className="stack gap-3">{[...Array(4)].map((_, i) => <Skeleton key={i} height={90} />)}</div>}

      {!error && !loading && items && (!items.length ? (
        <EmptyState title="No recommendations" message="Nothing needs attention right now for this view." />
      ) : (
        <div className="grid grid-cols-2">
          {items.map((r, i) => (
            <div className="rec-card fade-in" key={r.recommendation_id ?? i}>
              <div className="rec-card-header">
                <span className="text-micro">{tab === "forecast" ? "FORECAST-BASED" : "CURRENT-STATE"}</span>
                <StatusBadge status={r.severity} />
              </div>
              <div className="text-h2" style={{ fontSize: 15, marginBottom: 2 }}>{r.recommendation_type}</div>
              <div className="text-small" style={{ fontWeight: 600, marginBottom: 6 }}>{r.medicine_name || r.medicine_id}</div>
              <p className="text-small">{r.why}</p>
              {r.inputs && (
                <div className="row gap-2 wrap" style={{ marginTop: 10 }}>
                  {Object.entries(r.inputs).slice(0, 4).map(([k, v]) => (
                    <span key={k} className="rec-input-chip">{k.replace(/_/g, " ")}: {typeof v === "number" ? v.toLocaleString() : String(v)}</span>
                  ))}
                </div>
              )}
              {r.recommended_action && <p className="text-small" style={{ marginTop: 8, fontWeight: 600 }}>→ {r.recommended_action}</p>}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
