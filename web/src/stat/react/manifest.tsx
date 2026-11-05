import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useMemo } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import type { ApiState } from "@/api/envelope";
import { fetchManifest } from "@/stat/lib/api";
import type { Manifest } from "@/stat/lib/schemas/manifest";

export type ManifestValue = {
  manifest: Manifest | null;
  /** Seasons the data has, oldest first; drives the season chips and the model's catalog. */
  seasons: number[];
};

export const ManifestContext = createContext<ManifestValue>({ manifest: null, seasons: [] });

const MANIFEST_QUERY_KEY = ["stat-manifest"] as const;

/** The one manifest query every stat UI shares (same key, so one fetch), without the Provider's boundary. */
export function useManifestQuery() {
  return useQuery({ queryKey: MANIFEST_QUERY_KEY, queryFn: fetchManifest, retry: false, refetchOnWindowFocus: false });
}

export function seasonsOf(manifest: Manifest): number[] {
  return [...new Set(manifest.seasons.map((s) => s.season))].sort((a, b) => a - b);
}

/** The manifest and its seasons; empty until the provider's query has loaded. */
export function useManifest(): ManifestValue {
  return useContext(ManifestContext);
}

/**
 * Loads the data manifest and renders its children only once it is ready, so the season chips match
 * the data. Loading and failure show in the content area, with a retry; the nav stays usable.
 */
export function ManifestProvider({ children }: { children: ReactNode }) {
  const query = useManifestQuery();
  const state: ApiState<Manifest> = query.data
    ? { kind: "ready", data: query.data }
    : query.error
      ? { kind: "error", error: { message: query.error.message, code: null }, retry: () => void query.refetch() }
      : { kind: "loading" };
  return <ApiBoundary state={state}>{(manifest) => <Ready manifest={manifest}>{children}</Ready>}</ApiBoundary>;
}

function Ready({ manifest, children }: { manifest: Manifest; children: ReactNode }) {
  const value = useMemo(() => ({ manifest, seasons: seasonsOf(manifest) }), [manifest]);
  return <ManifestContext.Provider value={value}>{children}</ManifestContext.Provider>;
}
