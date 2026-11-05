import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { fetchEnvelope } from "@/api/envelope";
import type { components } from "@/api/schema";
import type { LeaguePointsRow } from "@/stat/engine/leaguePointsQuery";

type PointsRow = components["schemas"]["PlayerPointsRow"];

export type LeaguePointsState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; rows: LeaguePointsRow[] };

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
        const who = id === null ? "" : `&gsis_id=${encodeURIComponent(id)}`;
        const envelope = await fetchEnvelope<PointsRow[]>(
          `/api/leagues/${encodeURIComponent(league ?? "")}/player-points?season=${season}${who}`,
        );
        if (envelope.status !== "ok" || envelope.data === null) {
          throw new Error(envelope.error?.message ?? "League points did not load.");
        }
        return envelope.data.map((r) => ({ ...r, season }));
      },
      retry: 1,
      staleTime: POINTS_STALE_MS,
      refetchOnWindowFocus: false,
    })),
  });
  // The state is rebuilt only when a query's data or error changes, so callers can depend on it.
  const signature = [league, ...wanted.map((w) => `${w.season}:${w.id}`), ...queries.map((q) => `${q.dataUpdatedAt}:${q.errorUpdatedAt}`)].join("|");
  return useMemo((): LeaguePointsState => {
    if (queries.length === 0) return { kind: "idle" };
    const failed = queries.find((q) => q.error);
    if (failed) return { kind: "error", message: failed.error?.message ?? "League points did not load." };
    if (queries.some((q) => q.data === undefined)) return { kind: "loading" };
    return { kind: "ready", rows: queries.flatMap((q) => q.data ?? []) };
  }, [signature, queries.length]);
}
