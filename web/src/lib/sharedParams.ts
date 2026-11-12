/** Query parameters every page shares: the viewed league and team, and the global week. Nothing else crosses pages. */
const SHARED_KEYS: readonly string[] = ["league", "team", "week"];

/** Copies the shared keys present in `from` into `to`. */
export function copyShared(from: URLSearchParams, to: URLSearchParams): void {
  SHARED_KEYS.forEach((key) => {
    const value = from.get(key);
    if (value !== null) to.set(key, value);
  });
}
