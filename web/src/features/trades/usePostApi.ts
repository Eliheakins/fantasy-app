import { useQuery } from "@tanstack/react-query";
import { type ApiState, fetchEnvelope, pollInterval, resolveState } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { withTeam } from "@/lib/team";
import { useTeam } from "@/lib/teamContext";

/**
 * POST a simulation route and poll it while the server says "running". The result stays in the
 * query cache under `key`, so it survives navigation and is not re-fetched on focus or remount.
 * `body` null keeps the query off.
 */
export function usePostApi<T>(
  key: readonly unknown[],
  path: string,
  body: unknown | null,
): { state: ApiState<T> | null; refetch: () => void } {
  const { team, league } = useTeam();
  const url = withTeam(path, team, league);
  const query = useQuery<Envelope<T>, Error>({
    queryKey: ["post", ...key, url],
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
