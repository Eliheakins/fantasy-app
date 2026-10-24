import { useQuery } from "@tanstack/react-query";
import { type ApiState, fetchEnvelope, pollInterval, resolveState } from "@/api/envelope";
import type { Envelope } from "@/api/types";

/** GET an /api route. Polls every 2 s while the server says "running". */
export function useApi<T>(url: string | null): ApiState<T> {
  const query = useQuery<Envelope<T>, Error>({
    queryKey: ["api", url],
    queryFn: () => fetchEnvelope<T>(url ?? ""),
    enabled: url !== null,
    refetchInterval: (q) => (q.state.error ? false : pollInterval(q.state.data)),
    retry: 1,
  });
  if (url === null) return { kind: "loading" };
  return resolveState(query.data, query.error);
}
