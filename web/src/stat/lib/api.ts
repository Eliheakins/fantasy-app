import { BUILD_DATA_HINT, DATA_BASE_URL, joinUrl, START_API_HINT } from "@/stat/lib/config";
import { requestJson } from "@/stat/lib/http";
import { type Manifest, manifestSchema } from "@/stat/lib/schemas/manifest";

/** The data folder's table of contents (seasons, files, freshness), written by the data build. */
export function fetchManifest(): Promise<Manifest> {
  return requestJson(joinUrl(DATA_BASE_URL, "manifest.json"), manifestSchema, {
    what: "the data manifest",
    unreachableHint: START_API_HINT,
    notFoundHint: BUILD_DATA_HINT,
    shapeHint: "Rebuild the data.",
    // no-store: after a rebuild the next load must see the new seasons, not a cached copy.
    init: { cache: "no-store" },
  });
}
