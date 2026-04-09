import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { initDB } from "@/shared/lib/duckdb";
import { useWorkbenchStore } from "@/stores/useWorkbenchStore";

/**
 * Boots DuckDB-WASM once for Explore / Ask / Formulas routes.
 */
export function WorkbenchLayout() {
  const isEngineReady = useWorkbenchStore((s) => s.isEngineReady);
  const setEngineReady = useWorkbenchStore((s) => s.setEngineReady);
  const [engineError, setEngineError] = useState<string | null>(null);

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
      {!isEngineReady && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-surface/95 backdrop-blur-sm pt-14">
          {engineError ? (
            <p className="max-w-md px-4 text-center text-sm text-danger-fg">
              DuckDB failed to start: {engineError}
            </p>
          ) : (
            <>
              <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <p className="text-sm text-ink-muted">Starting DuckDB-WASM…</p>
            </>
          )}
        </div>
      )}
      <Outlet />
    </div>
  );
}
