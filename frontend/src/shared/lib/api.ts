import {
  type PlayerDictionaryRow,
  playerDictionarySchema,
} from "@/shared/lib/schemas/playerDictionary";
import type { NFLPlayer } from "@/shared/types/workbench";

// Not 8000, so the API does not collide with other local dev servers.
export const API_BASE = "http://localhost:8100";

export interface PbpShardInfo {
  year: number;
  path: string;
}

export interface PlayerDetailPayload {
  player: NFLPlayer;
  shards: PbpShardInfo[];
}

export async function searchPlayers(q: string): Promise<NFLPlayer[]> {
  const params = new URLSearchParams({ q });
  const res = await fetch(`${API_BASE}/search?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Search failed: ${res.status}`);
  }
  return res.json() as Promise<NFLPlayer[]>;
}

export async function fetchPbpShards(): Promise<PbpShardInfo[]> {
  const res = await fetch(`${API_BASE}/pbp/shards`);
  if (!res.ok) {
    throw new Error(`PBP shards failed: ${res.status}`);
  }
  return res.json() as Promise<PbpShardInfo[]>;
}

export async function fetchPlayerDetail(gsisId: string): Promise<PlayerDetailPayload> {
  const res = await fetch(`${API_BASE}/player/${encodeURIComponent(gsisId)}`);
  if (res.status === 404) {
    throw new Error("Player not found");
  }
  if (!res.ok) {
    throw new Error(`Player fetch failed: ${res.status}`);
  }
  return res.json() as Promise<PlayerDetailPayload>;
}

export function shardParquetUrl(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

let dictionaryPromise: Promise<PlayerDictionaryRow[]> | null = null;

async function loadPlayerDictionary(): Promise<PlayerDictionaryRow[]> {
  const res = await fetch(`${API_BASE}/players/dictionary`);
  if (!res.ok) {
    throw new Error(`Player dictionary failed: ${res.status}`);
  }
  const parsed = playerDictionarySchema.safeParse(await res.json());
  if (!parsed.success) {
    throw new Error(`Unexpected player dictionary shape (${parsed.error.message})`);
  }
  return parsed.data;
}

/** Fetched once per session; a failed load is not cached so the next ask retries. */
export function fetchPlayerDictionary(): Promise<PlayerDictionaryRow[]> {
  dictionaryPromise ??= loadPlayerDictionary().catch((e: unknown) => {
    dictionaryPromise = null;
    throw e;
  });
  return dictionaryPromise;
}
