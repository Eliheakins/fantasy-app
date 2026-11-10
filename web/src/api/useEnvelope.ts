import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiFailure, type ApiState, fetchEnvelope, pollInterval, resolveState } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { withTeam } from "@/lib/team";
import { useTeam } from "@/lib/teamContext";

/**
 * The react-query wrappers around `fetchEnvelope`, in one place. GET queries share the key
 * ["api", url], so a url read by two callers is fetched once; POST results sit under ["post", ...].
 */

type ApiQueryOptions = {
  /** Poll at this interval instead of following the server's "running" state (2 s). */
  refetchMs?: number;
  /** Keep polling after a failed fetch (the game-day block keeps its last update on screen). */
  pollOnError?: boolean;
};

/** The query options every GET shares: key, fetch, one retry, polling while the server says "running". */
function apiQueryOptions<T>(url: string, { refetchMs, pollOnError = false }: ApiQueryOptions = {}) {
  return {
    queryKey: ["api", url] as const,
    queryFn: () => fetchEnvelope<T>(url),
    refetchInterval: (q: { state: { error: unknown; data: Envelope<T> | undefined } }) =>
      q.state.error && !pollOnError ? false : (refetchMs ?? pollInterval(q.state.data)),
    retry: 1,
  };
}

/** GET an /api route, as the viewed team when one is chosen. A null path keeps the query off. */
export function useEnvelopeQuery<T>(path: string | null, refetchMs?: number): ApiState<T> {
  const { team, league } = useTeam();
  const url = path === null ? null : withTeam(path, team, league); // so the team is part of the query key
  const query = useQuery<Envelope<T>, Error>({ ...apiQueryOptions<T>(url ?? "", { refetchMs }), enabled: url !== null });
  if (url === null) return { kind: "loading" };
  const state = resolveState(query.data, query.error);
  return state.kind === "error" ? { ...state, retry: () => void query.refetch() } : state;
}

/** One GET per url, as sent (no `?team=` added); a null url is off and reads as loading. */
export function useEnvelopeQueries<T>(urls: readonly (string | null)[]): ApiState<T>[] {
  return useQueries({
    queries: urls.map((url) => ({ ...apiQueryOptions<T>(url ?? ""), enabled: url !== null })),
    combine: (results) => results.map((r, i): ApiState<T> => (urls[i] === null ? { kind: "loading" } : resolveState(r.data, r.error))),
  });
}

/** A GET with the last good data kept on a failed refetch; polls every `refetchMs` even after an error. */
export function useEnvelopePolling<T>(url: string, refetchMs: number) {
  const q = useQuery<Envelope<T>, Error>(apiQueryOptions<T>(url, { refetchMs, pollOnError: true }));
  const stale = Boolean(q.data && q.error);
  return { state: resolveState(q.data, stale ? null : q.error), stale };
}

/**
 * POST a simulation route and poll it while the server says "running". The result stays in the
 * query cache under `key`, so it survives navigation and is not re-fetched on focus or remount.
 * `body` null keeps the query off.
 */
export function usePostEnvelope<T>(
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

/** POST a route once on demand, then refetch every GET (the kept ["post", ...] results stay). */
export function useEnvelopeMutation<T>(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const env = await fetchEnvelope<T>(path, { method: "POST" });
      if (env.status !== "ok") throw new ApiFailure(env.error?.message ?? "Refresh failed", env.error?.code);
      return env.data;
    },
    onSuccess: () => client.invalidateQueries({ predicate: (q) => q.queryKey[0] === "api" }),
  });
}

/** An ok envelope's data, or an Error with the server's message; for callers that cache the data itself. */
export async function fetchEnvelopeData<T>(url: string, failure: string): Promise<T> {
  const envelope = await fetchEnvelope<T>(url);
  if (envelope.status !== "ok" || envelope.data === null) throw new Error(envelope.error?.message ?? failure);
  return envelope.data;
}
