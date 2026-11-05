import { useQueries } from "@tanstack/react-query";
import { type ApiState, fetchEnvelope, pollInterval, resolveState } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { leagueUrl } from "@/features/home/hooks";

/**
 * One GET per league, whatever the league select says and always for my own team (no `?team=`):
 * to-dos and visit changes are about my teams. Same query key as `useApi`, so the cache is shared.
 * A null path turns the queries off.
 */
export function useEachLeague<T>(leagueKeys: readonly string[], path: string | null): ApiState<T>[] {
  return useQueries({
    queries: leagueKeys.map((key) => {
      const url = path === null ? "" : leagueUrl(key, path);
      return {
        queryKey: ["api", url],
        queryFn: () => fetchEnvelope<T>(url),
        enabled: path !== null,
        refetchInterval: (q: { state: { error: unknown; data: Envelope<T> | undefined } }) =>
          q.state.error ? false : pollInterval(q.state.data),
        retry: 1,
      };
    }),
    combine: (results) =>
      results.map((r): ApiState<T> => (path === null ? { kind: "loading" } : resolveState(r.data, r.error))),
  });
}

export function useLeagueQuery<T>(leagueKey: string, path: string | null): ApiState<T> {
  return useEachLeague<T>([leagueKey], path)[0] ?? { kind: "loading" };
}
