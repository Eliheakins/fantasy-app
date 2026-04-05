import type { NFLPlayer } from "@/types/workbench";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const base = API_BASE.replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}
