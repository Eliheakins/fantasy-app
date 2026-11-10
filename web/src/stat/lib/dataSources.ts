import type { ColumnSource } from "@/stat/engine/columns";
import { DATA_BASE_URL, joinUrl } from "@/stat/lib/config";
import type { Manifest } from "@/stat/lib/schemas/manifest";

/**
 * A shard URL carries the build time as `?v=`: a rebuilt shard keeps its file name, and the loader
 * caches footers and chunks by URL.
 */
const shardUrl = (manifest: Manifest, path: string) => `${joinUrl(DATA_BASE_URL, path)}?v=${encodeURIComponent(manifest.built_at)}`;

/** One Parquet file per season in the manifest, addressed from the data base URL. */
export function seasonSources(manifest: Manifest | null): ColumnSource[] {
  if (!manifest) {
    return [];
  }
  return manifest.seasons.map((s) => ({ year: s.season, url: shardUrl(manifest, s.path) }));
}

/** The tier-1 table of per-game totals, when the build wrote it. The year is unused: it holds every season. */
export function playerGameSource(manifest: Manifest | null): ColumnSource | null {
  return manifest?.player_game ? { year: 0, url: shardUrl(manifest, manifest.player_game.path) } : null;
}

/** The player index (position, latest season, years of experience), for the position and rookie filters. */
export function playerIndexSource(manifest: Manifest | null): ColumnSource | null {
  return manifest?.player_index ? { year: 0, url: shardUrl(manifest, manifest.player_index.path) } : null;
}
