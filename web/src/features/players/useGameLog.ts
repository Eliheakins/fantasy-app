import { useQuery } from "@tanstack/react-query";
import { seasonsOf, useManifestQuery } from "@/stat/react/manifest";
import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { browserColumnStore } from "@/stat/engine/parquetColumns";
import { runStatQuery } from "@/stat/engine/statQuery";
import { playerGameSource, seasonSources } from "@/stat/lib/dataSources";
import type { QueryResult } from "@/stat/types/workbench";

/** The player's weekly regular-season totals for `season` from the stat engine. */
export function useGameLog(gsisId: string, statIds: readonly string[], season: number) {
  // The manifest is read first so its build time keys the result: a data rebuild is never served from cache.
  const manifestQuery = useManifestQuery();
  const manifest = manifestQuery.data;
  const log = useQuery<QueryResult, Error>({
    queryKey: ["player-game-log", gsisId, season, manifest?.built_at ?? null],
    enabled: manifest !== undefined,
    retry: false,
    queryFn: async ({ signal }) => {
      if (!manifest) throw new Error("The data manifest is not loaded.");
      return runStatQuery(
        {
          statIds: [...statIds],
          filterChipState: { [`season-${season}`]: true, "stype-reg": true },
          gsisIds: [gsisId],
          sources: seasonSources(manifest),
          playerGame: playerGameSource(manifest),
          granularity: "total",
          minPlays: 0,
          split: "week",
          chipGroups: buildFilterChipGroups(seasonsOf(manifest)),
        },
        browserColumnStore,
        signal,
      );
    },
  });
  if (manifestQuery.isError) return { data: undefined, isPending: false, isError: true as const, error: manifestQuery.error };
  return log;
}
