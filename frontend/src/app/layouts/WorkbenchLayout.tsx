import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { useManifestStore } from "@/stores/useManifestStore";

/**
 * Loads the data manifest once for the Explore and Ask routes. Routes render only after it is
 * ready, so the season chips match the data.
 */
export function WorkbenchLayout() {
  const manifestStatus = useManifestStore((s) => s.status);
  const manifestError = useManifestStore((s) => s.error);
  const loadManifest = useManifestStore((s) => s.load);

  useEffect(() => {
    void loadManifest();
  }, [loadManifest]);

  const isReady = manifestStatus === "ready";

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {!isReady && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-surface/95 backdrop-blur-sm pt-14">
          {manifestError ? (
            <>
              <p className="max-w-md px-4 text-center text-sm text-danger-fg">{manifestError}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => void loadManifest()}>
                Try again
              </Button>
            </>
          ) : (
            <>
              <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <p className="text-sm text-ink-muted">Starting up…</p>
            </>
          )}
        </div>
      )}
      {isReady && <Outlet />}
    </div>
  );
}
