import { DATA_BASE_URL, joinUrl, START_API_HINT } from "@/shared/lib/config";
import { requestJson } from "@/shared/lib/http";
import {
  type Player,
  type PlayerDictionaryRow,
  playersFileSchema,
} from "@/shared/lib/schemas/players";
import { useManifestStore } from "@/stores/useManifestStore";

const BUILD_HINT = "Build the data with: uv run python backend/scripts/build_data.py";

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

let playersPromise: Promise<Player[]> | null = null;
let dictionaryPromise: Promise<PlayerDictionaryRow[]> | null = null;

export function resetPlayersCache(): void {
  playersPromise = null;
  dictionaryPromise = null;
}

async function loadPlayers(): Promise<Player[]> {
  const entry = useManifestStore.getState().manifest?.players;
  if (!entry) {
    throw new Error(`No player list found in the data. ${BUILD_HINT}`);
  }
  const file = await requestJson(joinUrl(DATA_BASE_URL, entry.path), playersFileSchema, {
    what: "the player list",
    unreachableHint: START_API_HINT,
    notFoundHint: BUILD_HINT,
    shapeHint: "Rebuild the data.",
  });
  return file.players;
}

/** Fetched once per session; a failed load is not cached so the next use retries. */
export function getPlayers(): Promise<Player[]> {
  playersPromise ??= loadPlayers().catch((e: unknown) => {
    playersPromise = null;
    throw e;
  });
  return playersPromise;
}

/** Built once from the same list, so name matching keeps its per-array index cache. */
export function getPlayerDictionary(): Promise<PlayerDictionaryRow[]> {
  dictionaryPromise ??= getPlayers()
    .then(playerDictionary)
    .catch((e: unknown) => {
      dictionaryPromise = null;
      throw e;
    });
  return dictionaryPromise;
}

/** The players with these ids, in the order asked; unknown ids are skipped. */
export async function getPlayersByIds(ids: readonly string[]): Promise<Player[]> {
  const byId = new Map((await getPlayers()).map((p) => [p.gsis_id, p]));
  return ids.flatMap((id) => {
    const player = byId.get(id);
    return player ? [player] : [];
  });
}
