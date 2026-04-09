import type { PbpShardInfo } from "@/shared/lib/api";
import {
  initDB,
  mountGoldLayer,
  mountMicroscopeCfbPbpView,
  mountMicroscopePbpView,
  mountRemoteShard,
  runQuery,
} from "@/shared/lib/duckdb";
import type { QueryResult } from "@/shared/types/workbench";

/** Track A (Explore / Formula microscope): per-year `nfl_pbp_YYYY` views from pinned shard list. */
export async function ensureExploreOrFormulaPbpMounted(
  shards: PbpShardInfo[],
  toUrl: (path: string) => string,
): Promise<void> {
  await initDB();
  for (const s of shards) {
    await mountRemoteShard(toUrl(s.path), `nfl_pbp_${s.year}`);
  }
}

export async function ensureGoldTelescopeMounted(
  playerHubUrl: string,
  goldUnifiedUrl: string,
): Promise<void> {
  await initDB();
  await mountGoldLayer(playerHubUrl, goldUnifiedUrl);
}

export async function ensureNlqNflMicroscopeMounted(httpParquetUrls: string[]): Promise<void> {
  await initDB();
  await mountMicroscopePbpView(httpParquetUrls);
}

export async function ensureNlqCfbMicroscopeMounted(httpParquetUrls: string[]): Promise<void> {
  await initDB();
  await mountMicroscopeCfbPbpView(httpParquetUrls);
}

export async function runWorkbenchQuery(sql: string): Promise<QueryResult> {
  return runQuery(sql);
}

export { initDB, runQuery };
