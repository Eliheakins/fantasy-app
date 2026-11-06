import { EMPTY_QUERY, MAX_PINNED_PLAYERS, type QueryState } from "@/stat/lib/queryUrl";
import { type QueryIntent } from "@/stat/lib/nlqApi";
import { specFromIntent, unsupportedReasons } from "@/stat/lib/querySpec";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import type { Side, Split } from "@/stat/types/queryBuilder";
import type { AnswerPath } from "../interpretQuestion";
import { withDefaultSeasonType } from "../intentFilters";
import { type Leaderboard, splitAsked } from "../ruleParser";
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
): { filters: string[]; lastGames: number | null; notes: string[] } {
  const time = readTime(asked, scope);
  const merged = withTime(filters, time);
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

/** Answers with the named players and the intent's stats and filters, unless the engine cannot run them. */
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
  const blocked = unsupportedReasons(specFromIntent({ ...intent, stat_ids: stats }, ids));
  if (blocked.length > 0) {
    actions.fail(asked, path, blocked.join(" "));
    return;
  }
  const split = splitOf(asked);
  const time = timeOf(intent.filter_ids, asked, scope, split);
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

/** Answers a league ranking or a team question the rules read with no player to match, so no model call. */
export function showRules(
  intent: QueryIntent,
  board: Leaderboard | undefined,
  team: { ids: string[]; side: Side } | undefined,
  asked: string,
  actions: AskActions,
  scope: TimeScope,
): void {
  const subject = team ? ({ kind: "team" } as const) : ({ kind: "players", positions: [] } as const);
  const stats = settleStats(intent.stat_ids, subject);
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
  };
  actions.answer(next, asked, "rules", [], time.notes);
}
