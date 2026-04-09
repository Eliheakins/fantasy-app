import {
  fetchCfbPbpShards,
  fetchPbpShards,
  shardParquetUrl,
  type PbpShardInfo,
} from "@/shared/lib/api";
import {
  ensureNlqCfbMicroscopeMounted,
  ensureNlqNflMicroscopeMounted,
} from "@/shared/lib/workbenchDuckdb";

export type NlqMicroscopeMountFailure =
  | { code: "fetch"; message: string; detail?: string }
  | { code: "empty"; message: string; detail?: string }
  | { code: "mount"; message: string; detail?: string };

export async function mountNlqMicroscopeTrack(
  track: "microscope_nfl" | "microscope_cfb",
): Promise<NlqMicroscopeMountFailure | null> {
  const fetchShards = track === "microscope_nfl" ? fetchPbpShards : fetchCfbPbpShards;
  let shards: PbpShardInfo[];
  try {
    shards = await fetchShards();
  } catch (e) {
    return {
      code: "fetch",
      message:
        track === "microscope_nfl"
          ? "Could not load PBP shards from the API."
          : "Could not load CFB PBP shards from the API.",
      detail: e instanceof Error ? e.message : String(e),
    };
  }
  if (shards.length === 0) {
    return {
      code: "empty",
      message:
        track === "microscope_nfl"
          ? "No PBP Parquet shards are configured. Add nfl_pbp_YYYY.parquet under /data or set R2 + PBP_YEARS."
          : "No CFB PBP Parquet shards are configured. Add cfb_pbp_YYYY.parquet under /data or configure R2 for CFB.",
    };
  }
  const urls = shards.map((s) => shardParquetUrl(s.path));
  try {
    if (track === "microscope_nfl") {
      await ensureNlqNflMicroscopeMounted(urls);
    } else {
      await ensureNlqCfbMicroscopeMounted(urls);
    }
  } catch (e) {
    return {
      code: "mount",
      message:
        track === "microscope_nfl"
          ? "Microscope PBP data could not be mounted in DuckDB-WASM."
          : "CFB Microscope PBP data could not be mounted in DuckDB-WASM.",
      detail: e instanceof Error ? e.message : String(e),
    };
  }
  return null;
}
