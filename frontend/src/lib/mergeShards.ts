import type { PbpShardInfo } from "@/lib/api";

/** One shard per season year (API paths are identical for the same year). */
export function mergeShardMap(map: Record<string, PbpShardInfo[]>): PbpShardInfo[] {
  const byYear = new Map<number, PbpShardInfo>();
  for (const list of Object.values(map)) {
    for (const s of list) {
      byYear.set(s.year, s);
    }
  }
  return [...byYear.values()].sort((a, b) => a.year - b.year);
}
