import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { fetchEnvelopeData } from "@/api/useEnvelope";
import type { LeaguePointsRow } from "@/stat/engine/leaguePointsQuery";

export type LeaguePointsState =
  { kind: "idle" } | { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; rows: LeaguePointsRow[] };

/** Points change only when `make refresh` rebuilds `player_points`, so five minutes is fresh enough. */
const POINTS_STALE_MS = 5 * 60 * 1000;

/**
 * Regular-season weekly points under one league's scoring, per season asked about: the named
 * players' (one request each) or, with no names, everyone's. The key has no manifest `built_at`:
 * the points come from the fantasy API's `player_points`, not from the stat shards a rebuild replaces.
 * Idle (nothing fetched) unless a league is picked and there is a season to ask about.
 */
export function useLeaguePoints(
  league: string | null,
  seasons: readonly number[],
  gsisIds: readonly string[] | null = null,
): LeaguePointsState {
  const named: (string | null)[] = gsisIds && gsisIds.length > 0 ? [...gsisIds] : [null];
  const wanted = league === null ? [] : seasons.flatMap((season) => named.map((id) => ({ season, id })));
  const queries = useQueries({
    queries: wanted.map(({ season, id }) => ({
      queryKey: ["league-points", league, season, id],
      queryFn: async (): Promise<LeaguePointsRow[]> => {
        const data = await fetchEnvelopeData(
          "/api/leagues/{league}/player-points",
          { path: { league: league ?? "" }, query: { season, gsis_id: id ?? undefined } },
          "League points did not load.",
        );
        return data.map((r) => ({ ...r, season }));
      },
      retry: 1,
      staleTime: POINTS_STALE_MS,
      refetchOnWindowFocus: false,
    })),
  });
  // The state is rebuilt only when a query's data or error changes, so callers can depend on it.
  const signature = [
    league,
    ...wanted.map((w) => `${w.season}:${w.id}`),
    ...queries.map((q) => `${q.dataUpdatedAt}:${q.errorUpdatedAt}`),
  ].join("|");
  return useMemo((): LeaguePointsState => {
    if (queries.length === 0) return { kind: "idle" };
    const failed = queries.find((q) => q.error);
    if (failed) return { kind: "error", message: failed.error?.message ?? "League points did not load." };
    if (queries.some((q) => q.data === undefined)) return { kind: "loading" };
    return { kind: "ready", rows: queries.flatMap((q) => q.data ?? []) };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `queries` is a new array each render; `signature` tracks its contents
  }, [signature, queries.length]);
}
