import { usePlayerStatQuery } from "./usePlayerStatQuery";

/** The player's weekly regular-season totals for `season` from the stat engine. */
export function useGameLog(gsisId: string, statIds: readonly string[], season: number) {
  return usePlayerStatQuery("player-game-log", [gsisId], statIds, season, "week");
}
