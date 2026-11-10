import { useQuery } from "@tanstack/react-query";
import type { ApiState } from "@/api/envelope";
import { useManifestQuery } from "@/stat/react/manifest";
import { getPlayersByIds } from "@/stat/lib/players";

export type PlayerInfo = Awaited<ReturnType<typeof getPlayersByIds>>[number];

/** The player with this id from the stat data's player list; ready with null when the id is unknown. */
export function usePlayer(gsisId: string): ApiState<PlayerInfo | null> {
  const manifestQuery = useManifestQuery();
  const manifest = manifestQuery.data;
  const query = useQuery<PlayerInfo | null, Error>({
    queryKey: ["player-info", gsisId, manifest?.built_at ?? null],
    enabled: manifest !== undefined,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => (await getPlayersByIds(manifest ?? null, [gsisId]))[0] ?? null,
  });
  if (manifestQuery.isError) return failed(manifestQuery.error.message, () => void manifestQuery.refetch());
  if (query.isError) return failed(query.error.message, () => void query.refetch());
  return query.isPending ? { kind: "loading" } : { kind: "ready", data: query.data };
}

function failed(message: string, retry: () => void): ApiState<never> {
  return { kind: "error", error: { message, code: null }, retry };
}

/** Of these ids, those the stat data knows, in order; null until that is read. One lookup for the whole list. */
export function useKnownIds(gsisIds: readonly string[]): string[] | null {
  const manifestQuery = useManifestQuery();
  const manifest = manifestQuery.data;
  const query = useQuery<string[], Error>({
    queryKey: ["known-ids", gsisIds, manifest?.built_at ?? null],
    enabled: manifest !== undefined && gsisIds.length > 0,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const found = new Set((await getPlayersByIds(manifest ?? null, [...gsisIds])).map((p) => p.gsis_id));
      return gsisIds.filter((id) => found.has(id));
    },
  });
  return query.data ?? null;
}
