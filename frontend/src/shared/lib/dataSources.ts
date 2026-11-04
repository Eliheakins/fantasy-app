import type { ColumnSource } from "@/shared/engine/columns";
import { DATA_BASE_URL, joinUrl } from "@/shared/lib/config";
import type { Manifest } from "@/shared/lib/schemas/manifest";

/** One Parquet file per season in the manifest, addressed from the data base URL. */
export function seasonSources(manifest: Manifest | null): ColumnSource[] {
  return (manifest?.seasons ?? []).map((s) => ({ year: s.season, url: joinUrl(DATA_BASE_URL, s.path) }));
}
