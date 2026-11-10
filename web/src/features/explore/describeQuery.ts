import type { QueryState } from "@/stat/lib/queryUrl";

const POSITION_NAMES = { QB: "quarterbacks", RB: "running backs", WR: "wide receivers", TE: "tight ends" } as const;
const ROSTER_PHRASES = { mine: "on my roster now", rostered: "on a roster now", fa: "who are free agents now" } as const;
const GRANULARITY_PHRASES = { total: " in total", per_game: " per game", per_play: " per play" } as const;
const SPLIT_PHRASES = { season: "one row per season", week: "one row per week", location: "home and away rows" } as const;

export interface QueryWords {
  /** Display name of each selected stat, in the order of `state.stats`. */
  statNames: readonly string[];
  /** Labels of the season chips that are on. */
  seasonLabels: readonly string[];
}

const joinWords = (words: readonly string[]): string =>
  words.length <= 2 ? words.join(" and ") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;

/** The query as one plain sentence, e.g. "Top 25 wide receivers by Targets per game in 2026, with at least 20 plays." */
export function describeQuery(state: QueryState, words: QueryWords): string {
  if (state.stats.length === 0) {
    return "Pick a stat to start.";
  }
  const group =
    state.subject === "teams" ? "teams" : `${state.rookie ? "rookie " : ""}${state.position ? POSITION_NAMES[state.position] : "players"}`;
  const gran = GRANULARITY_PHRASES[state.granularity];
  const rankedBy = state.order ? words.statNames[state.stats.indexOf(state.order.metric)] : undefined;
  const lead =
    state.order && state.limit !== null && rankedBy
      ? `${state.order.direction === "desc" ? "Top" : "Bottom"} ${state.limit} ${group} by ${rankedBy}${gran}`
      : `${joinWords(words.statNames)}${gran} for ${group}`;
  const when = words.seasonLabels.length > 0 ? ` in ${joinWords(words.seasonLabels)}` : " across every season";
  const extras = [
    state.roster ? ROSTER_PHRASES[state.roster] : null,
    state.lastGames ? `last ${state.lastGames} games` : null,
    state.minPlays > 0 ? `at least ${state.minPlays} plays` : null,
    state.split ? SPLIT_PHRASES[state.split] : null,
  ].filter((x): x is string => x !== null);
  return `${lead}${when}${extras.length > 0 ? `, ${extras.join(", ")}` : ""}.`;
}
