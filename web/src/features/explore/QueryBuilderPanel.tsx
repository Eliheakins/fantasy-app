import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { defaultQuery, isBlankQuery } from "@/features/explore/defaultQuery";
import { describeQuery } from "@/features/explore/describeQuery";
import { ExploreResultsCanvas } from "@/features/explore/ExploreResultsCanvas";
import { IgnoredFiltersNotice } from "@/features/explore/IgnoredFiltersNotice";
import { ParticipationNotice } from "@/features/explore/ParticipationNotice";
import { QueryBar } from "@/features/explore/QueryBar";
import { SavedSearches } from "@/features/explore/SavedSearches";
import { useExplorePlayerSearch } from "@/features/explore/useExplorePlayerSearch";
import { useExploreQueryExecution } from "@/features/explore/useExploreQueryExecution";
import { useLeagueName } from "@/lib/league";
import { getStatById } from "@/stat/config/statDictionary";
import { dataThrough } from "@/stat/lib/dataFreshness";
import { statLabel } from "@/stat/lib/queryBuilder";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useManifest } from "@/stat/react/manifest";
import { rememberExplore } from "@/stat/react/routeMemory";
import { useQueryState } from "@/stat/react/useQueryState";

/** Find players: one query bar of chips over full-width results. A bare page opens on a useful query. */
export function QueryBuilderPanel() {
  const playerSearch = useExplorePlayerSearch();
  const queryExec = useExploreQueryExecution();
  const { manifest, seasons } = useManifest();
  const { search } = useLocation();
  const { state, replaceQuery } = useQueryState();
  const leagueName = useLeagueName();
  const chipGroups = useFilterChipGroups();
  const freshness = dataThrough(manifest);
  const latestSeason = seasons[seasons.length - 1];

  // The Find players link returns here with the same query after a visit to another page.
  useEffect(() => rememberExplore(search), [search]);

  // A page opened with no query shows the default once; clearing everything afterwards stays cleared.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || latestSeason === undefined) return;
    opened.current = true;
    if (isBlankQuery(state)) replaceQuery(defaultQuery(latestSeason));
  }, [latestSeason, state, replaceQuery]);

  const seasonGroup = chipGroups.find((g) => g.id === "season");
  const summary = describeQuery(state, {
    statNames: state.stats.map((id) => {
      const stat = getStatById(id);
      return stat ? statLabel(stat, leagueName) : id;
    }),
    seasonLabels: (seasonGroup?.options ?? []).filter((o) => state.filters.includes(o.id)).map((o) => o.label),
  });

  return (
    <>
      <PageHeader title="Find players" subtitle={freshness ? `Data through ${freshness}.` : undefined} />
      <section aria-label="Your query" className="mb-6 space-y-3 rounded-xl border border-line bg-surface p-4">
        <QueryBar playerSearch={{ ...playerSearch, pinnedCount: playerSearch.pinnedPlayers.length }} />
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
          <p className="min-w-0 flex-1 basis-80 text-body text-label">{summary}</p>
          <button
            type="button"
            onClick={() => latestSeason !== undefined && replaceQuery(defaultQuery(latestSeason))}
            className="min-h-11 px-3 text-body font-semibold text-focus underline"
          >
            Reset
          </button>
        </div>
        <SavedSearches />
      </section>
      <div className="min-w-0 space-y-5">
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
    </>
  );
}
