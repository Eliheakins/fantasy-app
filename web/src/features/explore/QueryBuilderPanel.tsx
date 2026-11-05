import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { ExploreMobileBuilderDrawer } from "@/features/explore/ExploreMobileBuilderDrawer";
import { ExploreResultsCanvas } from "@/features/explore/ExploreResultsCanvas";
import { IgnoredFiltersNotice } from "@/features/explore/IgnoredFiltersNotice";
import { useManifest } from "@/features/explore/manifest";
import { ParticipationNotice } from "@/features/explore/ParticipationNotice";
import {
  QueryBuilderSidebarExecuteFooter,
  QueryBuilderSidebarScroll,
} from "@/features/explore/QueryBuilderSidebarBody";
import { rememberExplore } from "@/features/explore/routeMemory";
import { useExplorePlayerSearch } from "@/features/explore/useExplorePlayerSearch";
import { useExploreQueryExecution } from "@/features/explore/useExploreQueryExecution";
import { dataThrough } from "@/stat/lib/dataFreshness";

/** Guided query UI: builder sidebar (who / what / context) beside the results. */
export function QueryBuilderPanel() {
  const playerSearch = useExplorePlayerSearch();
  const queryExec = useExploreQueryExecution();
  const { manifest } = useManifest();
  const { search } = useLocation();
  const freshness = dataThrough(manifest);

  // The Find players link returns here with the same query after a visit to another page.
  useEffect(() => rememberExplore(search), [search]);

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
    <>
      <PageHeader
        title="Explore"
        subtitle={
          <>
            Pin players, pick metrics, and filter context; results update below.
            {freshness ? ` Data through ${freshness}.` : ""}
          </>
        }
      />
      <div className="lg:grid lg:grid-cols-[360px_1fr] lg:items-start lg:gap-6">
        <aside
          aria-label="Query builder"
          className="card-flat hidden flex-col lg:sticky lg:top-4 lg:flex lg:max-h-[calc(100dvh-2rem)]"
        >
          <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto pb-4">
            <QueryBuilderSidebarScroll {...sidebarScrollProps} />
          </div>
          <QueryBuilderSidebarExecuteFooter running={queryExec.running} onExecute={onExecute} className="px-0 pb-0" />
        </aside>
        <div className="min-w-0 space-y-5">
          <ExploreMobileBuilderDrawer sidebarScrollProps={sidebarScrollProps} running={queryExec.running} onExecute={onExecute} />
          <IgnoredFiltersNotice />
          <ParticipationNotice />
          <ExploreResultsCanvas
            result={queryExec.result}
            error={queryExec.error}
            details={queryExec.details}
            running={queryExec.running}
            pinnedPlayers={queryExec.pinnedPlayers}
            namedPlayers={queryExec.namedPlayers}
          />
        </div>
      </div>
    </>
  );
}
