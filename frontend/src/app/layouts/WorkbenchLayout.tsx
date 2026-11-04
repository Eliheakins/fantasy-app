import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { initDB } from "@/shared/lib/duckdb";
import { describeStartupError } from "@/shared/lib/startupError";
import { useManifestStore } from "@/stores/useManifestStore";
import { useWorkbenchStore } from "@/stores/useWorkbenchStore";

/**
 * Boots DuckDB-WASM and loads the data manifest once for the Explore and Ask routes.
 * Routes render only after both are ready, so the season chips match the data.
 */
export function WorkbenchLayout() {
  const isEngineReady = useWorkbenchStore((s) => s.isEngineReady);
  const setEngineReady = useWorkbenchStore((s) => s.setEngineReady);
  const [engineError, setEngineError] = useState<string | null>(null);
  const manifestStatus = useManifestStore((s) => s.status);
  const manifestError = useManifestStore((s) => s.error);
  const loadManifest = useManifestStore((s) => s.load);

  useEffect(() => {
    void loadManifest();
  }, [loadManifest]);

  const isReady = isEngineReady && manifestStatus === "ready";
  const startupError = describeStartupError(manifestError, engineError);

  useEffect(() => {
    let cancelled = false;
    void initDB()
      .then(() => {
        if (!cancelled) {
          setEngineError(null);
          setEngineReady(true);
        }
      })
      .catch((e) => {
        console.error(e);
        if (!cancelled) {
          setEngineReady(false);
          setEngineError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [setEngineReady]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {!isReady && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-surface/95 backdrop-blur-sm pt-14">
          {startupError ? (
            <>
              <p className="max-w-md px-4 text-center text-sm text-danger-fg">{startupError}</p>
              {manifestError ? (
                <Button type="button" variant="outline" size="sm" onClick={() => void loadManifest()}>
                  Try again
                </Button>
              ) : null}
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
