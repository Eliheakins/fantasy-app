import { usePlayerStatQuery } from "./usePlayerStatQuery";

/** One row per player: the season's regular-season totals for these stats. */
export function useSeasonTotals(gsisIds: readonly string[], statIds: readonly string[], season: number) {
  return usePlayerStatQuery("season-totals", gsisIds, statIds, season);
}
