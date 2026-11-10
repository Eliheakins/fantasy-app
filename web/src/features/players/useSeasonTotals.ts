import { useQuery } from "@tanstack/react-query";
import { seasonsOf, useManifestQuery } from "@/stat/react/manifest";
import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { browserColumnStore } from "@/stat/engine/parquetColumns";
import { runStatQuery } from "@/stat/engine/statQuery";
import { playerGameSource, seasonSources } from "@/stat/lib/dataSources";
import type { QueryResult } from "@/stat/types/workbench";

/** One row per player: the season's regular-season totals for these stats. */
export function useSeasonTotals(gsisIds: readonly string[], statIds: readonly string[], season: number) {
  const manifestQuery = useManifestQuery();
  const manifest = manifestQuery.data;
  return useQuery<QueryResult, Error>({
    queryKey: ["season-totals", gsisIds, statIds, season, manifest?.built_at ?? null],
    enabled: manifest !== undefined && gsisIds.length > 0 && statIds.length > 0,
    retry: false,
    queryFn: async ({ signal }) => {
      if (!manifest) throw new Error("The data manifest is not loaded.");
      return runStatQuery(
        {
          statIds: [...statIds],
          filterChipState: { [`season-${season}`]: true, "stype-reg": true },
          gsisIds: [...gsisIds],
          sources: seasonSources(manifest),
          playerGame: playerGameSource(manifest),
          granularity: "total",
          minPlays: 0,
          chipGroups: buildFilterChipGroups(seasonsOf(manifest)),
        },
        browserColumnStore,
        signal,
      );
    },
  });
}
