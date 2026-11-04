import { DATA_BASE_URL, DATA_UNREACHABLE_HINT, joinUrl } from "@/shared/lib/config";
import { requestJson } from "@/shared/lib/http";
import { type Manifest, manifestSchema } from "@/shared/lib/schemas/manifest";

/** The data folder's table of contents (seasons, files, freshness), written by the data build. */
export function fetchManifest(): Promise<Manifest> {
  return requestJson(joinUrl(DATA_BASE_URL, "manifest.json"), manifestSchema, {
    what: "the data manifest",
    unreachableHint: DATA_UNREACHABLE_HINT,
    notFoundHint: "Build the data with: uv run python backend/scripts/build_data.py",
    shapeHint: "Rebuild the data.",
    // no-store: after a rebuild the next load must see the new seasons, not a cached copy.
    init: { cache: "no-store" },
  });
}
