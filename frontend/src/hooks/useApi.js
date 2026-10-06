import { useEffect, useState, useCallback, useRef } from "react";
import { apiErrorMessage } from "../api/client";

/**
 * Generic data-fetching hook used by every page. Re-fetches whenever `deps` change
 * (typically filter state), tracks loading/error, and exposes refetch() for the
 * page-level Refresh button. Centralizing this keeps every screen's loading/error/
 * empty handling consistent, instead of each page re-implementing fetch/try/catch.
 */
export function useApi(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const seq = useRef(0);

  const load = useCallback(() => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    fetcher()
      .then((res) => { if (id === seq.current) setData(res); })
      .catch((err) => { if (id === seq.current) setError(apiErrorMessage(err)); })
      .finally(() => { if (id === seq.current) setLoading(false); });
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  return { data, loading, error, refetch: load };
}
