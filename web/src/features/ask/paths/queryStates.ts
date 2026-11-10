import { isLeagueStat } from "@/stat/engine/leaguePointsQuery";
import { EMPTY_QUERY, MAX_PINNED_PLAYERS, type QueryState } from "@/stat/lib/queryUrl";
import { type QueryIntent } from "@/stat/lib/nlqApi";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import type { Side, Split } from "@/stat/types/queryBuilder";
import type { AnswerPath } from "../interpretQuestion";
import { withDefaultSeasonType } from "../intentFilters";
import { readOpponents } from "../opponents";
import { leaderboardFor } from "../ranking";
import { tokenize } from "../resolvePlayers";
import { asksRanking, type Leaderboard, splitAsked, teamsAsked } from "../ruleParser";
import { settleStats } from "../settleStats";
import { readTime, type TimeScope, withTime } from "../timeWords";
import type { AskActions } from "./types";

/** "by season" and "each game" split the answer, whichever path read the rest of the question. */
const splitOf = (question: string): Split | null => {
  const split = splitAsked(question);
  return split === "both" ? null : split;
};

/** Situations so rare in one season (playoffs, weather) that a question naming only them means every season. */
const RARE_CHIPS = new Set(["stype-post", "wind-gte15", "temp-lte32"]);

/**
 * The time a question covers. Time words read in code replace the model's reading of them. A question
 * that names no season gets the current one, and the notes say so: summing every season silently gave
 * career totals to questions that meant this year. "Career", a split by season and rare situations
 * keep every season.
 */
export function timeOf(
  filters: readonly string[],
  asked: string,
  scope: TimeScope,
  split: Split | null,
  playerNamed = false,
): { filters: string[]; lastGames: number | null; notes: string[] } {
  const time = readTime(asked, scope);
  // Opponents are read in code too; "home vs away" is a split, so its two chips are not filters.
  const merged = [...new Set([...withTime(filters, time), ...readOpponents(asked, playerNamed).filters])].filter(
    (f) => !(split === "location" && f.startsWith("loc-")),
  );
  const notes = [...time.notes];
  const first = Math.min(...scope.seasons);
  const current = Math.max(...scope.seasons);
  if (scope.seasons.length > 0 && !merged.some((f) => f.startsWith("season-")) && split !== "season") {
    if (time.career) {
      notes.push(`Career here means ${first} on: the play-by-play data starts in ${first}.`);
    } else if (merged.some((f) => RARE_CHIPS.has(f))) {
      notes.push(`No season named, so every season from ${first} to ${current} counts.`);
    } else {
      merged.push(`season-${current}`);
      notes.push(`No season named, so this is ${current}, the current season.`);
    }
  }
  return { filters: withDefaultSeasonType(merged), lastGames: time.lastGames, notes };
}

/** Answers with the named players and the intent's stats and filters. */
export function showIntent(
  players: PlayerDictionaryRow[],
  intent: QueryIntent,
  asked: string,
  path: AnswerPath,
  unrecognized: string[],
  actions: AskActions,
  scope: TimeScope,
): void {
  const ids = [...new Set(players.map((p) => p.gsis_id))].slice(0, MAX_PINNED_PLAYERS);
  const stats = settleStats(intent.stat_ids, { kind: "players", positions: players.map((p) => p.position) });
  const split = splitOf(asked);
  const time = timeOf(intent.filter_ids, asked, scope, split, true);
  const next: QueryState = {
    ...EMPTY_QUERY,
    players: ids,
    stats,
    filters: time.filters,
    granularity: intent.granularity,
    minPlays: 0,
    order: null,
    limit: null,
    split,
    lastGames: time.lastGames,
  };
  actions.answer(next, asked, path, unrecognized, time.notes);
}

export const NO_PLAYER_MESSAGE =
  "I couldn't find a player or team in that question. Name a player by last or full name, like " +
  "“Mahomes passing yards 2023”, a team, like “Chiefs passing yards 2023”, or ask for a leaderboard like " +
  "“who led the league in passing yards in 2023”.";

/**
 * The model's reading of a question that names no player. It is a ranking when the words ask for one
 * ("most", "top", "leads") or the model read one, ordered by its first stat as the rules would; a team
 * named or "which team" makes it about teams. Anything else names no one, and is refused.
 */
export function showModelRanking(
  intent: QueryIntent,
  asked: string,
  path: AnswerPath,
  unrecognized: string[],
  actions: AskActions,
  scope: TimeScope,
): void {
  const team = teamsAsked(asked);
  const ranked = asksRanking(asked) || intent.ranking === true;
  if (team && team.ids.length > 0) {
    showRules(intent, undefined, team, asked, actions, scope, path, unrecognized);
    return;
  }
  if (!ranked) {
    actions.fail(asked, path, NO_PLAYER_MESSAGE);
    return;
  }
  const subject = team ? ({ kind: "team" } as const) : ({ kind: "players", positions: [] } as const);
  const metric = settleStats([intent.stat_ids[0]!], subject)[0]!;
  const board = leaderboardFor(tokenize(asked.replace(/%/g, " percent ")), metric, intent.granularity, {
    teams: team !== null,
    defense: team?.side === "defense",
    weekly: splitOf(asked) === "week",
  });
  if ("reason" in board) {
    actions.fail(asked, path, board.reason);
    return;
  }
  const rankedIntent = { ...intent, stat_ids: [...new Set([board.order.metric, ...intent.stat_ids.slice(1)])] };
  showRules(rankedIntent, board, team ?? undefined, asked, actions, scope, path, unrecognized);
}

/** Answers a league ranking or a team question with no player to match (read by the rules, or by the model). */
export function showRules(
  intent: QueryIntent,
  board: Leaderboard | undefined,
  team: { ids: string[]; side: Side } | undefined,
  asked: string,
  actions: AskActions,
  scope: TimeScope,
  path: AnswerPath = "rules",
  unrecognized: string[] = [],
): void {
  // A ranking of one position reads generic stats as that position's own ("top running backs by EPA").
  const subject = team ? ({ kind: "team" } as const) : ({ kind: "players", positions: board?.position ? [board.position] : [] } as const);
  const stats = settleStats(intent.stat_ids, subject);
  if (team && stats.some(isLeagueStat)) {
    actions.fail(asked, path, "League points are for players, not teams.");
    return;
  }
  const order = board ? { ...board.order, metric: settleStats([board.order.metric], subject)[0]! } : null;
  const split = splitOf(asked);
  const time = timeOf(intent.filter_ids, asked, scope, split);
  const next: QueryState = {
    ...EMPTY_QUERY,
    subject: team ? "teams" : "players",
    teams: team?.ids ?? [],
    side: team?.side ?? "offense",
    stats,
    filters: time.filters,
    granularity: intent.granularity,
    minPlays: board?.minPlays ?? 0,
    order,
    limit: board?.limit ?? null,
    split,
    lastGames: time.lastGames,
    position: board?.position ?? null,
    rookie: board?.rookie ?? false,
  };
  actions.answer(next, asked, path, unrecognized, time.notes);
}
