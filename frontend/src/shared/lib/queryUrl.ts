/**
 * The query the user is looking at, as URL parameters: `?p=<player>&s=<stat>&f=<filter>&g=<granularity>&m=<min plays>`
 * with one `p`, `s` and `f` per value. The URL is the single source of truth, so reload, back/forward
 * and shared links all restore the same result. Everything read from a URL is untrusted and is
 * cleaned here: unknown ids are dropped, lists are capped, numbers are clamped.
 */
import { getStatById } from "@/shared/config/statDictionary";
import type { GranularityMode } from "@/shared/types/queryBuilder";

/** Max metrics selectable at once (matches the model's cap in `MAX_INTENT_STATS`). */
export const MAX_SELECTED_STATS = 5;
export const MAX_PINNED_PLAYERS = 5;
export const MAX_MIN_PLAYS = 500;
export const DEFAULT_GRANULARITY: GranularityMode = "per_play";

export interface QueryState {
  /** GSIS ids of the pinned players. */
  players: string[];
  stats: string[];
  /** Filter chip ids that are on. */
  filters: string[];
  granularity: GranularityMode;
  minPlays: number;
}

export const EMPTY_QUERY: QueryState = {
  players: [],
  stats: [],
  filters: [],
  granularity: DEFAULT_GRANULARITY,
  minPlays: 0,
};

const KEYS = { players: "p", stats: "s", filters: "f", granularity: "g", minPlays: "m" } as const;
const GRANULARITIES: readonly GranularityMode[] = ["total", "per_game", "per_play"];
const PLAYER_ID = /^[\w-]{1,24}$/;
const FILTER_ID = /^[\w-]{1,40}$/;

const unique = (values: readonly string[]): string[] => [...new Set(values)];

/** A rate stat has no total or per-game form, so it forces per-play. */
function clampGranularity(stats: readonly string[], granularity: GranularityMode): GranularityMode {
  const anyRate = stats.some((id) => getStatById(id)?.rate_only);
  return anyRate && granularity !== "per_play" ? "per_play" : granularity;
}

function clampMinPlays(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(MAX_MIN_PLAYS, Math.round(value))) : 0;
}

/**
 * Reads the query from URL parameters. `knownFilterIds` (the chips the current data has) lets it drop
 * filters that no longer exist; without it any well-formed id is kept.
 */
export function parseQuery(params: URLSearchParams, knownFilterIds?: ReadonlySet<string>): QueryState {
  const stats = unique(params.getAll(KEYS.stats).filter((id) => getStatById(id))).slice(0, MAX_SELECTED_STATS);
  const requested = params.get(KEYS.granularity);
  const granularity = GRANULARITIES.find((g) => g === requested) ?? DEFAULT_GRANULARITY;

  return {
    players: unique(params.getAll(KEYS.players).filter((id) => PLAYER_ID.test(id))).slice(0, MAX_PINNED_PLAYERS),
    stats,
    filters: unique(
      params.getAll(KEYS.filters).filter((id) => FILTER_ID.test(id) && (!knownFilterIds || knownFilterIds.has(id))),
    ),
    granularity: clampGranularity(stats, granularity),
    minPlays: clampMinPlays(Number(params.get(KEYS.minPlays) ?? 0)),
  };
}

/** `base` with its query parameters replaced by `state`; other parameters (like `q`) are kept. */
export function writeQuery(base: URLSearchParams, state: QueryState): URLSearchParams {
  const next = new URLSearchParams(base);
  for (const key of Object.values(KEYS)) {
    next.delete(key);
  }
  state.players.forEach((id) => next.append(KEYS.players, id));
  state.stats.forEach((id) => next.append(KEYS.stats, id));
  state.filters.forEach((id) => next.append(KEYS.filters, id));
  if (state.granularity !== DEFAULT_GRANULARITY) {
    next.set(KEYS.granularity, state.granularity);
  }
  if (state.minPlays > 0) {
    next.set(KEYS.minPlays, String(state.minPlays));
  }
  return next;
}

export function serializeQuery(state: QueryState): URLSearchParams {
  return writeQuery(new URLSearchParams(), state);
}

// ---- transitions: each returns a new state and leaves its input alone --------------------------

export function toggleStat(state: QueryState, id: string): QueryState {
  if (!getStatById(id)) {
    return state;
  }
  const has = state.stats.includes(id);
  if (!has && state.stats.length >= MAX_SELECTED_STATS) {
    return state;
  }
  const stats = has ? state.stats.filter((s) => s !== id) : [...state.stats, id];
  return { ...state, stats, granularity: clampGranularity(stats, state.granularity) };
}

export function setGranularity(state: QueryState, granularity: GranularityMode): QueryState {
  return { ...state, granularity: clampGranularity(state.stats, granularity) };
}

export function setMinPlays(state: QueryState, minPlays: number): QueryState {
  return { ...state, minPlays: clampMinPlays(minPlays) };
}

export function toggleFilter(state: QueryState, id: string): QueryState {
  const filters = state.filters.includes(id) ? state.filters.filter((f) => f !== id) : [...state.filters, id];
  return { ...state, filters };
}

/** Sets the chips of one group to exactly `selectedIds`; chips of other groups stay as they are. */
export function applyFilterGroup(
  state: QueryState,
  groupOptionIds: readonly string[],
  selectedIds: readonly string[],
): QueryState {
  const others = state.filters.filter((f) => !groupOptionIds.includes(f));
  return { ...state, filters: [...others, ...selectedIds.filter((id) => groupOptionIds.includes(id))] };
}

export function pinPlayer(state: QueryState, id: string): QueryState {
  if (state.players.includes(id) || state.players.length >= MAX_PINNED_PLAYERS || !PLAYER_ID.test(id)) {
    return state;
  }
  return { ...state, players: [...state.players, id] };
}

export function unpinPlayer(state: QueryState, id: string): QueryState {
  return { ...state, players: state.players.filter((p) => p !== id) };
}

export function clearPins(state: QueryState): QueryState {
  return { ...state, players: [] };
}
