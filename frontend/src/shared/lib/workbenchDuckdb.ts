import type { PbpShardInfo } from "@/shared/lib/api";
import { initDB, mountRemoteShard, runQuery } from "@/shared/lib/duckdb";
import type { QueryResult } from "@/shared/types/workbench";

/** Explore and Ask: per-year `nfl_pbp_YYYY` views from the pinned players' shard list. */
export async function ensurePbpMounted(
  shards: PbpShardInfo[],
  toUrl: (path: string) => string,
): Promise<void> {
  await initDB();
  for (const s of shards) {
    await mountRemoteShard(toUrl(s.path), `nfl_pbp_${s.year}`);
  }
}

export async function runWorkbenchQuery(sql: string): Promise<QueryResult> {
  return runQuery(sql);
}

export { initDB, runQuery };
