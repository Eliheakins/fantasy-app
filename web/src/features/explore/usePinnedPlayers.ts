import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useManifest } from "@/stat/react/manifest";
import { getPlayersByIds } from "@/stat/lib/players";
import type { NFLPlayer } from "@/stat/types/workbench";

/**
 * The pinned players in URL order. The URL holds only ids, so names come from the player list;
 * until they load (or if an id is not in the list) the entry shows the id.
 */
export function usePinnedPlayers(ids: readonly string[]): NFLPlayer[] {
  const { manifest } = useManifest();
  const key = ids.join(",");
  const { data } = useQuery({
    queryKey: ["pinned-players", manifest?.built_at ?? null, key],
    queryFn: () => getPlayersByIds(manifest, ids),
    enabled: ids.length > 0,
    placeholderData: keepPreviousData,
  });

  const byId = new Map((data ?? []).map((p) => [p.gsis_id, p]));
  return ids.map((id): NFLPlayer => byId.get(id) ?? { gsis_id: id, full_name: null, position: null, team: null, headshot_url: null });
}
