import { useQuery } from "@tanstack/react-query";
import { seasonsOf, useManifestQuery } from "@/stat/react/manifest";
import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { browserColumnStore } from "@/stat/engine/parquetColumns";
import { runStatQuery } from "@/stat/engine/statQuery";
import { playerGameSource, seasonSources } from "@/stat/lib/dataSources";
import type { Split } from "@/stat/types/queryBuilder";
import type { QueryResult } from "@/stat/types/workbench";

/** Regular-season totals for these players and stats in `season`, optionally split (by week, say). */
export function usePlayerStatQuery(key: string, gsisIds: readonly string[], statIds: readonly string[], season: number, split?: Split) {
  // The manifest is read first so its build time keys the result: a data rebuild is never served from cache.
  const manifestQuery = useManifestQuery();
  const manifest = manifestQuery.data;
  const result = useQuery<QueryResult, Error>({
    queryKey: [key, gsisIds, statIds, season, manifest?.built_at ?? null],
    enabled: manifest !== undefined && gsisIds.length > 0,
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
          split,
          chipGroups: buildFilterChipGroups(seasonsOf(manifest)),
        },
        browserColumnStore,
        signal,
      );
    },
  });
  if (manifestQuery.isError) return { data: undefined, isPending: false, isError: true as const, error: manifestQuery.error };
  return result;
}
