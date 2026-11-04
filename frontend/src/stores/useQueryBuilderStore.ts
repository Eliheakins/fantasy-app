import { create } from "zustand";

import { type FilterChipGroup, getAllFilterChipIds } from "@/shared/config/queryBuilderOptions";
import { getStatById } from "@/shared/config/statDictionary";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import type { GranularityMode } from "@/shared/types/queryBuilder";

const DEFAULT_GRANULARITY: GranularityMode = "per_play";

/** Max metrics selectable in The What (multi-select). */
export const MAX_SELECTED_STATS = 5;

export type { GranularityMode };

/** Drop unknown or removed stat IDs (e.g. after dictionary changes). Empty selection is allowed. */
function sanitizeSelectedStatIds(ids: string[]): string[] {
  return [...new Set(ids.filter((id) => getStatById(id)))];
}

function clampGranularityForStats(statIds: string[], g: GranularityMode): GranularityMode {
  const anyRate = statIds.some((id) => getStatById(id)?.rate_only);
  if (anyRate && (g === "total" || g === "per_game")) {
    return "per_play";
  }
  return g;
}

export interface QueryBuilderState {
  selectedStatIds: string[];
  activeGranularity: GranularityMode;
  minPlays: number;
  filterChipState: Record<string, boolean>;
  toggleStatId: (id: string) => void;
  setActiveGranularity: (g: GranularityMode) => void;
  setMinPlays: (n: number) => void;
  toggleFilterChip: (id: string) => void;
  applyFilterGroup: (group: FilterChipGroup, selectedIds: string[]) => void;
  /** Replace stats, filters and granularity in one update (Ask), so only one query runs. */
  applyIntent: (intent: { statIds: string[]; filterIds: string[]; granularity: GranularityMode }) => void;
  resetQueryBuilder: () => void;
}

export const useQueryBuilderStore = create<QueryBuilderState>((set) => ({
  selectedStatIds: [],
  activeGranularity: DEFAULT_GRANULARITY,
  minPlays: 0,
  filterChipState: {},
  toggleStatId: (id) =>
    set((s) => {
      const has = s.selectedStatIds.includes(id);
      let next = has
        ? s.selectedStatIds.filter((x) => x !== id)
        : s.selectedStatIds.length >= MAX_SELECTED_STATS
          ? s.selectedStatIds
          : [...s.selectedStatIds, id];
      next = sanitizeSelectedStatIds([...new Set(next)]);
      const nextG = clampGranularityForStats(next, s.activeGranularity);
      return { selectedStatIds: next, activeGranularity: nextG };
    }),
  setActiveGranularity: (g) =>
    set((s) => ({
      activeGranularity: clampGranularityForStats(s.selectedStatIds, g),
    })),
  setMinPlays: (n) => set({ minPlays: Math.max(0, Math.min(500, Math.round(n))) }),
  toggleFilterChip: (id) =>
    set((s) => ({
      filterChipState: { ...s.filterChipState, [id]: !s.filterChipState[id] },
    })),
  applyFilterGroup: (group, selectedIds) =>
    set((s) => {
      const next = { ...s.filterChipState };
      for (const opt of group.options) {
        next[opt.id] = selectedIds.includes(opt.id);
      }
      return { filterChipState: next };
    }),
  applyIntent: ({ statIds, filterIds, granularity }) =>
    set(() => {
      const next = sanitizeSelectedStatIds(statIds).slice(0, MAX_SELECTED_STATS);
      return {
        selectedStatIds: next,
        activeGranularity: clampGranularityForStats(next, granularity),
        minPlays: 0,
        filterChipState: Object.fromEntries(
          getAllFilterChipIds(getFilterChipGroups()).map((id) => [id, filterIds.includes(id)]),
        ),
      };
    }),
  resetQueryBuilder: () =>
    set({
      selectedStatIds: [],
      activeGranularity: DEFAULT_GRANULARITY,
      minPlays: 0,
      filterChipState: Object.fromEntries(
        getAllFilterChipIds(getFilterChipGroups()).map((id) => [id, false]),
      ),
    }),
}));
