export type SavedSearch = { name: string; query: string };

const STORAGE_KEY = "fantasy.savedSearches";
/** The viewed league, team and week belong to the shell, not to a saved query. */
const SHELL_KEYS = ["league", "team", "week"];
/** Also dropped from a saved query: the Ask question that produced it. */
const EPHEMERAL_KEYS = [...SHELL_KEYS, "q"];
export const MAX_SAVED = 50;
export const MAX_NAME_LENGTH = 60;
const MAX_QUERY_LENGTH = 2000;

const isSaved = (v: unknown): v is SavedSearch =>
  typeof v === "object" && v !== null && typeof (v as SavedSearch).name === "string" && typeof (v as SavedSearch).query === "string";
const isSane = (s: SavedSearch): boolean => s.name.length <= MAX_NAME_LENGTH && s.query.length <= MAX_QUERY_LENGTH;

/** Saved searches from localStorage; empty when storage is unavailable or holds something else. */
export function readSaved(): SavedSearch[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isSaved).filter(isSane).slice(0, MAX_SAVED) : [];
  } catch {
    return [];
  }
}

/** True when stored; false when storage refused (private mode, full), so the caller can say so. */
export function writeSaved(list: readonly SavedSearch[]): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

export function queryWithoutShell(search: string): string {
  const params = new URLSearchParams(search);
  EPHEMERAL_KEYS.forEach((k) => params.delete(k));
  return params.toString();
}

/** The list with this query under `name`, replacing a search of the same name; a blank or over-long name, an
 * over-long query, or a 51st search changes nothing. */
export function addSaved(list: readonly SavedSearch[], name: string, search: string): SavedSearch[] {
  const trimmed = name.trim();
  const entry = { name: trimmed, query: queryWithoutShell(search) };
  const next = [...list.filter((s) => s.name !== trimmed), entry];
  return !trimmed || !isSane(entry) || next.length > MAX_SAVED ? [...list] : next;
}

export const removeSaved = (list: readonly SavedSearch[], name: string): SavedSearch[] => list.filter((s) => s.name !== name);

/** Find players with the saved query and the current league, team and week. */
export function savedHref(saved: SavedSearch, currentSearch: string): string {
  const params = new URLSearchParams(saved.query);
  const current = new URLSearchParams(currentSearch);
  SHELL_KEYS.forEach((k) => {
    const v = current.get(k);
    if (v !== null) params.set(k, v);
  });
  const text = params.toString();
  return text ? `/players/find?${text}` : "/players/find";
}
