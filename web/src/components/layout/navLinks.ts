import { lastExploreParams } from "@/features/explore/routeMemory";

/** Query parameters every page shares: the viewed league and team. Nothing else crosses pages. */
const SHARED_KEYS = ["league", "team"];

/**
 * The `search` for a nav link to `path`: league and team from the current URL, plus the last Explore query
 * for /explore (the current one while already there, since the memory is written after render).
 */
export function navSearch(path: string, currentSearch: string, currentPathname: string): string {
  const current = new URLSearchParams(currentSearch);
  const next = path !== "/explore" ? new URLSearchParams() : currentPathname === path ? new URLSearchParams(currentSearch) : lastExploreParams();
  SHARED_KEYS.forEach((key) => {
    const value = current.get(key);
    if (value !== null) next.set(key, value);
  });
  const text = next.toString();
  return text ? `?${text}` : "";
}
