import { useEffect, useState } from "react";

import { FormulaLab } from "@/components/FormulaLab";
import { QueryBuilderPanel } from "@/components/query-builder/QueryBuilderPanel";
import { initDB } from "@/lib/duckdb";
import { useWorkbenchStore } from "@/store/useWorkbenchStore";

export default function App() {
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
    <div className="relative min-h-screen bg-app text-ink">
      {!isEngineReady && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-surface/95 backdrop-blur-sm">
          {engineError ? (
            <p className="max-w-md text-center text-sm text-danger-fg">
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

      <QueryBuilderPanel>
        <FormulaLab />
      </QueryBuilderPanel>
    </div>
  );
}
