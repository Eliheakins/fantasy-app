import { lastExploreParams } from "@/features/explore/routeMemory";

/** Query parameters every page shares: the viewed league and team, and the global week. Nothing else crosses pages. */
const SHARED_KEYS = ["league", "team", "week"];

/**
 * The `search` for a nav link to `path`: league, team and week from the current URL, plus the last Explore query
 * for /players/find (the current one while already there, since the memory is written after render).
 */
export function navSearch(path: string, currentSearch: string, currentPathname: string): string {
  const current = new URLSearchParams(currentSearch);
  const next = path !== "/players/find" ? new URLSearchParams() : currentPathname === path ? new URLSearchParams(currentSearch) : lastExploreParams();
  SHARED_KEYS.forEach((key) => {
    const value = current.get(key);
    if (value !== null) next.set(key, value);
  });
  const text = next.toString();
  return text ? `?${text}` : "";
}
