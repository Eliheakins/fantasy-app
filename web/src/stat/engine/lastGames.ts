/**
 * "Last N games": for each player (or team), the games kept are its latest `n` by season then week,
 * among the games the scope allows (season, season type and week chips). Each path reports its own
 * games through `visit`, so play rows and one-row-per-game tables share the rule.
 */
export function latestGames(
  n: number,
  visit: (add: (id: string, game: unknown, season: number, week: number) => void) => void,
): Map<string, Set<unknown>> {
  const seen = new Map<string, Map<unknown, number>>();
  visit((id, game, season, week) => {
    let games = seen.get(id);
    if (!games) {
      games = new Map();
      seen.set(id, games);
    }
    games.set(game, season * 100 + week);
  });
  return new Map(
    [...seen].map(([id, games]) => [
      id,
      new Set(
        [...games]
          .sort((a, b) => b[1] - a[1])
          .slice(0, n)
          .map(([game]) => game),
      ),
    ]),
  );
}
