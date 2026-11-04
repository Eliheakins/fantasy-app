import { create } from "zustand";

import { fetchManifest } from "@/shared/lib/api";
import type { Manifest } from "@/shared/lib/schemas/manifest";

export type ManifestStatus = "idle" | "loading" | "ready" | "error";

interface ManifestState {
  manifest: Manifest | null;
  /** Seasons the data has, oldest first; drives the season chips and the model's catalog. */
  seasons: number[];
  status: ManifestStatus;
  error: string | null;
  load: () => Promise<void>;
}

export const useManifestStore = create<ManifestState>((set, get) => ({
  manifest: null,
  seasons: [],
  status: "idle",
  error: null,
  load: async () => {
    // StrictMode and layout remounts call this twice; a second call must not flip the app
    // back to "loading" (which would unmount the routes) or fetch again.
    const { status } = get();
    if (status === "loading" || status === "ready") {
      return;
    }
    set({ status: "loading", error: null });
    try {
      const manifest = await fetchManifest();
      const seasons = [...new Set(manifest.seasons.map((s) => s.season))].sort((a, b) => a - b);
      set({ manifest, seasons, status: "ready", error: null });
    } catch (e) {
      set({
        manifest: null,
        seasons: [],
        status: "error",
        error: e instanceof Error ? e.message : String(e),
      });
    }
  },
}));
