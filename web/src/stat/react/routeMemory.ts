/** Query-string keys that belong to the shell (the viewed league, team and week), not to an Explore query. */
const SHELL_KEYS = ["league", "team", "week"];

let exploreParams = "";

/** Remembers the last Explore query (without league and team) so the Find players link returns to it. */
export function rememberExplore(search: string): void {
  const params = new URLSearchParams(search);
  SHELL_KEYS.forEach((key) => params.delete(key));
  exploreParams = params.toString();
}

export function lastExploreParams(): URLSearchParams {
  return new URLSearchParams(exploreParams);
}
