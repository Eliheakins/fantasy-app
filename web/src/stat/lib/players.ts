import { BUILD_DATA_HINT, DATA_BASE_URL, joinUrl, START_API_HINT } from "@/stat/lib/config";
import { requestJson } from "@/stat/lib/http";
import type { Manifest } from "@/stat/lib/schemas/manifest";
import { type Player, type PlayerDictionaryRow, playersFileSchema } from "@/stat/lib/schemas/players";

export function playerDictionary(players: readonly Player[]): PlayerDictionaryRow[] {
  return players.map((p) => ({
    gsis_id: p.gsis_id,
    display_name: p.full_name,
    search_key: p.full_name.toLowerCase(),
    position: p.position,
    team: p.team,
  }));
}

/** Players whose name contains `query` (case-insensitive), for the Explore search box. */
export function searchPlayers(players: readonly Player[], query: string, limit = 10): Player[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return [];
  }
  return players.filter((p) => p.full_name.toLowerCase().includes(needle)).slice(0, limit);
}

/** Same file name after every rebuild, so the key is the file plus the manifest's build time. */
const buildKey = (manifest: Manifest | null): string | null =>
  manifest?.players ? `${manifest.players.path}|${manifest.built_at}` : null;

/** Remembers the latest load per build; a failed load is dropped so the next use retries. */
function cachePerBuild<T>(load: (manifest: Manifest | null) => Promise<T>): (manifest: Manifest | null) => Promise<T> {
  let slot: { key: string; promise: Promise<T> } | null = null;
  return (manifest) => {
    const key = buildKey(manifest);
    if (key === null) {
      return load(manifest);
    }
    if (slot?.key !== key) {
      const promise: Promise<T> = load(manifest).catch((e: unknown) => {
        if (slot?.promise === promise) {
          slot = null;
        }
        throw e;
      });
      slot = { key, promise };
    }
    return slot.promise;
  };
}

async function loadPlayers(manifest: Manifest | null): Promise<Player[]> {
  const entry = manifest?.players;
  if (!entry) {
    throw new Error(`No player list found in the data. ${BUILD_DATA_HINT}`);
  }
  const file = await requestJson(joinUrl(DATA_BASE_URL, entry.path), playersFileSchema, {
    what: "the player list",
    unreachableHint: START_API_HINT,
    notFoundHint: BUILD_DATA_HINT,
    shapeHint: "Rebuild the data.",
    // Same file name after every rebuild: revalidate so a new list is never hidden by the cache.
    init: { cache: "no-cache" },
  });
  return file.players;
}

/** Fetched once per manifest build. */
export const getPlayers = cachePerBuild(loadPlayers);

/** Built once from the same list, so name matching keeps its per-array index cache. */
export const getPlayerDictionary = cachePerBuild(async (manifest) => playerDictionary(await getPlayers(manifest)));

/** The players with these ids, in the order asked; unknown ids are skipped. */
export async function getPlayersByIds(manifest: Manifest | null, ids: readonly string[]): Promise<Player[]> {
  const byId = new Map((await getPlayers(manifest)).map((p) => [p.gsis_id, p]));
  return ids.flatMap((id) => {
    const player = byId.get(id);
    return player ? [player] : [];
  });
}
