import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { getAllFilterChipIds } from "@/stat/config/queryBuilderOptions";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import {
  applyFilterGroup,
  ignoredFilterIds,
  parseQuery,
  pinPlayer,
  type Position,
  type QueryOrder,
  type QueryState,
  type RosterFilter,
  setGranularity,
  setMinPlays,
  setPosition,
  setRanking,
  setRoster,
  setSide,
  setSplit,
  setSubject,
  toggleFilter,
  toggleStat,
  toggleTeam,
  unpinPlayer,
  writeQuery,
} from "@/stat/lib/queryUrl";
import type { GranularityMode, Side, Split } from "@/stat/types/queryBuilder";

/**
 * The query shown on this page, read from and written to the URL. Every change is a navigation, so
 * back/forward and reload restore it; nothing here is held in a store.
 */
export function useQueryState() {
  const [params, setParams] = useSearchParams();
  const chipGroups = useFilterChipGroups();
  const knownFilterIds = useMemo(() => new Set(getAllFilterChipIds(chipGroups)), [chipGroups]);

  const state = useMemo(() => parseQuery(params, knownFilterIds), [params, knownFilterIds]);
  const ignoredFilters = useMemo(() => ignoredFilterIds(params, state), [params, state]);
  const filterChipState = useMemo(
    () => Object.fromEntries(state.filters.map((id) => [id, true])) as Record<string, boolean>,
    [state.filters],
  );

  // `replace` keeps rapid changes (a slider) from filling the history.
  const update = useCallback(
    (change: (current: QueryState) => QueryState, options: { replace?: boolean } = {}) => {
      setParams((prev) => writeQuery(prev, change(parseQuery(prev, knownFilterIds))), {
        replace: options.replace,
      });
    },
    [setParams, knownFilterIds],
  );

  /** Show a different query (Ask's answer), keeping the question and the viewed league and team. */
  const showQuery = useCallback(
    (next: QueryState, question: string) => {
      setParams((prev) => {
        const nextParams = writeQuery(prev, next);
        nextParams.set("q", question);
        return nextParams;
      });
    },
    [setParams],
  );

  /** Swap in a whole query without adding a history entry (the default query on a bare page). */
  const replaceQuery = useCallback((next: QueryState) => setParams((prev) => writeQuery(prev, next), { replace: true }), [setParams]);

  return {
    state,
    replaceQuery,
    question: params.get("q") ?? "",
    filterChipState,
    ignoredFilters,
    showQuery,
    toggleStatId: useCallback((id: string) => update((s) => toggleStat(s, id)), [update]),
    setActiveGranularity: useCallback((g: GranularityMode) => update((s) => setGranularity(s, g)), [update]),
    setMinPlays: useCallback((n: number) => update((s) => setMinPlays(s, n), { replace: true }), [update]),
    applyFilterGroup: useCallback(
      (optionIds: readonly string[], selectedIds: readonly string[]) => update((s) => applyFilterGroup(s, optionIds, selectedIds)),
      [update],
    ),
    setRanking: useCallback((order: QueryOrder | null, limit?: number) => update((s) => setRanking(s, order, limit)), [update]),
    setSplit: useCallback((split: Split | null) => update((s) => setSplit(s, split)), [update]),
    setSubject: useCallback((subject: QueryState["subject"]) => update((s) => setSubject(s, subject)), [update]),
    setRoster: useCallback((roster: RosterFilter | null) => update((s) => setRoster(s, roster)), [update]),
    setPosition: useCallback((position: Position | null) => update((s) => setPosition(s, position)), [update]),
    setSide: useCallback((side: Side) => update((s) => setSide(s, side)), [update]),
    toggleTeamId: useCallback((id: string) => update((s) => toggleTeam(s, id)), [update]),
    toggleFilterId: useCallback((id: string) => update((s) => toggleFilter(s, id)), [update]),
    pinPlayer: useCallback((id: string) => update((s) => pinPlayer(s, id)), [update]),
    unpinPlayer: useCallback((id: string) => update((s) => unpinPlayer(s, id)), [update]),
  };
}
