import { copyShared } from "@/lib/sharedParams";
import { lastExploreParams } from "@/stat/react/routeMemory";

/**
 * The `search` for a nav link to `path`: league, team and week from the current URL, plus the last Explore query
 * for /players/find (the current one while already there, since the memory is written after render).
 */
export function navSearch(path: string, currentSearch: string, currentPathname: string): string {
  const next =
    path !== "/players/find" ? new URLSearchParams() : currentPathname === path ? new URLSearchParams(currentSearch) : lastExploreParams();
  copyShared(new URLSearchParams(currentSearch), next);
  const text = next.toString();
  return text ? `?${text}` : "";
}
