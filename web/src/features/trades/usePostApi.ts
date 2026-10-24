import { useQuery } from "@tanstack/react-query";
import { type ApiState, fetchEnvelope, pollInterval, resolveState } from "@/api/envelope";
import type { Envelope } from "@/api/types";

/**
 * POST a simulation route and poll it while the server says "running". The result stays in the
 * query cache under `key`, so it survives navigation and is not re-fetched on focus or remount.
 * `body` null keeps the query off.
 */
export function usePostApi<T>(
  key: readonly unknown[],
  url: string,
  body: unknown | null,
): { state: ApiState<T> | null; refetch: () => void } {
  const query = useQuery<Envelope<T>, Error>({
    queryKey: ["post", ...key],
    queryFn: () =>
      fetchEnvelope<T>(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      }),
    enabled: body !== null,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: (q) => (q.state.error ? false : pollInterval(q.state.data)),
    retry: 1,
  });
  if (body === null && query.data === undefined) return { state: null, refetch: () => void query.refetch() };
  return { state: resolveState(query.data, query.error), refetch: () => void query.refetch() };
}
