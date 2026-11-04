import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { ExploreMobileBuilderDrawer } from "@/features/explore/ExploreMobileBuilderDrawer";
import { ExploreResultsCanvas } from "@/features/explore/ExploreResultsCanvas";
import {
  QueryBuilderSidebarExecuteFooter,
  QueryBuilderSidebarScroll,
} from "@/features/explore/QueryBuilderSidebarBody";
import { useExplorePlayerSearch } from "@/features/explore/useExplorePlayerSearch";
import { useExploreQueryExecution } from "@/features/explore/useExploreQueryExecution";
import { PageHeader } from "@/shared/components/PageHeader";
import { useRouteMemory } from "@/stores/useRouteMemory";

/**
 * Guided query UI: sidebar (who / what / context) + results canvas.
 */
export function QueryBuilderPanel() {
  const playerSearch = useExplorePlayerSearch();
  const queryExec = useExploreQueryExecution();
  const location = useLocation();
  const rememberExplore = useRouteMemory((s) => s.rememberExplore);

  // The "Explore" tab returns here with the same query after a visit to Ask.
  useEffect(() => {
    rememberExplore(location.search);
  }, [location.search, rememberExplore]);

  const [mobileBuilderOpen, setMobileBuilderOpen] = useState(false);
  const [mobileActiveSnap, setMobileActiveSnap] = useState<number | string | null>(1);

  const sidebarScrollProps = {
    query: playerSearch.query,
    setQuery: playerSearch.setQuery,
    debounced: playerSearch.debounced,
    suggestions: playerSearch.suggestions,
    isPinned: playerSearch.isPinned,
    pinnedPlayers: playerSearch.pinnedPlayers,
    onSelectPlayer: playerSearch.onSelectPlayer,
    pinMessage: playerSearch.pinMessage,
    searchError: playerSearch.searchError,
  };

  const onExecute = () => void queryExec.executeQuery();

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col bg-app lg:flex-row">
        <aside className="hidden w-full shrink-0 flex-col border-border bg-surface lg:flex lg:sticky lg:top-14 lg:h-[calc(100dvh-3.5rem)] lg:w-[360px] lg:border-r">
          <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-5">
            <QueryBuilderSidebarScroll {...sidebarScrollProps} />
          </div>
          <QueryBuilderSidebarExecuteFooter running={queryExec.running} onExecute={onExecute} />
        </aside>

        <main className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-28 pt-4 lg:space-y-6 lg:p-8 lg:pb-8">
          <PageHeader
            eyebrow="Workbench / Explore"
            title="Query builder"
            titleAs="h2"
            description={
              <>
                Pin players, pick metrics, and filter context. Results update below. On phones, tap the filter button to open
                the builder sheet. Use{" "}
                <Link to="/ask" className="font-medium text-ink underline-offset-2 hover:underline">
                  Ask
                </Link>{" "}
                for natural language.
              </>
            }
          />

          <ExploreResultsCanvas
            result={queryExec.result}
            error={queryExec.error}
            details={queryExec.details}
            running={queryExec.running}
            pinnedPlayers={queryExec.pinnedPlayers}
          />
        </main>
      </div>

      <ExploreMobileBuilderDrawer
        sidebarScrollProps={sidebarScrollProps}
        running={queryExec.running}
        onExecute={onExecute}
        open={mobileBuilderOpen}
        onOpenChange={setMobileBuilderOpen}
        activeSnapPoint={mobileActiveSnap}
        onActiveSnapChange={setMobileActiveSnap}
      />
    </div>
  );
}
