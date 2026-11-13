import { type QueryKey, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ApiData, apiUrl, type Empty, type Init, type LooseParams, type Method, type Params, type Route } from "@/api/client";
import { type ApiState, fetchEnvelopeAt, pollInterval, resolveState, sendEnvelope } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { withTeam } from "@/lib/team";
import { useTeam } from "@/lib/teamContext";

/**
 * The react-query wrappers around `fetchEnvelope`, in one place. Each call names a route template and its
 * params (`client.ts`), and the data type comes from the schema. GET queries share the key ["api", url]
 * (`apiKey`), so a url read by two callers is fetched once; POST results sit under ["post", ...].
 */

type GetRoute = Route<"get">;

/** A GET's params, or null to keep the query off; optional when the route needs none. */
type QueryArgs<P extends GetRoute> =
  Empty extends Params<P, "get">
    ? [params?: Params<P, "get"> | null, refetchMs?: number]
    : [params: Params<P, "get"> | null, refetchMs?: number];

/** The query key of a GET: ["api", the url it resolves to]. */
export const apiKey = (route: string, params: LooseParams = {}) => ["api", apiUrl(route, params)] as const;

type ApiQueryOptions = {
  /** Poll at this interval instead of following the server's "running" state (2 s). */
  refetchMs?: number;
  /** Keep polling after a failed fetch (the game-day block keeps its last update on screen). */
  pollOnError?: boolean;
};

/** The query options every GET shares: key, fetch, polling while the server says "running".
 * The one retry is the app client's default for ["api", ...] keys (`queryClient.ts`). */
function apiQueryOptions<T>(route: string, params: LooseParams, { refetchMs, pollOnError = false }: ApiQueryOptions = {}) {
  return {
    queryKey: apiKey(route, params),
    queryFn: () => fetchEnvelopeAt<T>("get", route, { params }),
    refetchInterval: (q: { state: { error: unknown; data: Envelope<T> | undefined } }) =>
      q.state.error && !pollOnError ? false : (refetchMs ?? pollInterval(q.state.data)),
  };
}

/** `useEnvelopeQuery` with the route's types erased, for wrappers whose route is generic (`lib/league.tsx`);
 * they pass `T` as the route's `ApiData`. */
export function useApiQuery<T>(route: string, params: LooseParams | null, refetchMs?: number): ApiState<T> {
  const { team, league } = useTeam();
  const sent = params === null ? null : withTeam(route, params, team, league); // so the team is part of the query key
  const query = useQuery<Envelope<T>, Error>({ ...apiQueryOptions<T>(route, sent ?? {}, { refetchMs }), enabled: sent !== null });
  if (sent === null) return { kind: "loading" };
  const state = resolveState(query.data, query.error);
  return state.kind === "error" ? { ...state, retry: () => void query.refetch() } : state;
}

/** GET an /api route, as the viewed team when one is chosen. Null params keep the query off. */
export function useEnvelopeQuery<P extends GetRoute>(route: P, ...[params = {}, refetchMs]: QueryArgs<P>): ApiState<ApiData<P, "get">> {
  return useApiQuery<ApiData<P, "get">>(route, params as LooseParams | null, refetchMs);
}

/** One GET of `route` per params, as sent (no `team` added); null params are off and read as loading. */
export function useApiQueries<T>(route: string, params: readonly (LooseParams | null)[]): ApiState<T>[] {
  return useQueries({
    queries: params.map((p) => ({ ...apiQueryOptions<T>(route, p ?? {}), enabled: p !== null })),
    combine: (results) => results.map((r, i): ApiState<T> => (params[i] === null ? { kind: "loading" } : resolveState(r.data, r.error))),
  });
}

/** A GET with the last good data kept on a failed refetch; polls every `refetchMs` even after an error. */
export function useEnvelopePolling<P extends GetRoute>(route: P, params: Params<P, "get">, refetchMs: number) {
  const q = useQuery<Envelope<ApiData<P, "get">>, Error>(apiQueryOptions(route, params as LooseParams, { refetchMs, pollOnError: true }));
  const stale = Boolean(q.data && q.error);
  return { state: resolveState(q.data, stale ? null : q.error), stale };
}

/**
 * POST a simulation route and poll it while the server says "running". The result stays in the
 * query cache under `key`, so it survives navigation and is not re-fetched on focus or remount.
 * `init` null keeps the query off.
 */
export function usePostEnvelope<P extends Route<"post">>(
  key: readonly unknown[],
  route: P,
  init: Init<P, "post"> | null,
): { state: ApiState<ApiData<P, "post">> | null; refetch: () => void } {
  const { team, league } = useTeam();
  const { params = {}, body } = (init ?? {}) as { params?: LooseParams; body?: unknown };
  const sent = withTeam(route, params, team, league);
  const query = useQuery<Envelope<ApiData<P, "post">>, Error>({
    queryKey: ["post", ...key, apiUrl(route, sent)],
    queryFn: () => fetchEnvelopeAt<ApiData<P, "post">>("post", route, { params: sent, body }),
    enabled: init !== null,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: (q) => (q.state.error ? false : pollInterval(q.state.data)),
  });
  if (init === null && query.data === undefined) return { state: null, refetch: () => void query.refetch() };
  return { state: resolveState(query.data, query.error), refetch: () => void query.refetch() };
}

/**
 * A write: `mutate(init)` sends the route with its params and body. It fails with the server's message,
 * or a plain sentence when the server cannot be reached; on success it refetches the queries under each of
 * `invalidates` (["api"] for every GET; the kept ["post", ...] results stay) and settles once they are back.
 */
export function useEnvelopeMutation<M extends Exclude<Method, "get">, P extends Route<M>>(
  method: M,
  route: P,
  invalidates: readonly QueryKey[] = [],
) {
  const client = useQueryClient();
  return useMutation<ApiData<P, M>, Error, Init<P, M>>({
    mutationFn: (init) => sendEnvelope<ApiData<P, M>>(method, route, init as { params?: LooseParams; body?: unknown }),
    onSuccess: () => Promise.all(invalidates.map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

/** An ok envelope's data, or an Error with the server's message; for callers that cache the data itself. */
export async function fetchEnvelopeData<P extends GetRoute>(
  route: P,
  params: Params<P, "get">,
  failure: string,
): Promise<ApiData<P, "get">> {
  const envelope = await fetchEnvelopeAt<ApiData<P, "get">>("get", route, { params: params as LooseParams });
  if (envelope.status !== "ok" || envelope.data === null) throw new Error(envelope.error?.message ?? failure);
  return envelope.data;
}
