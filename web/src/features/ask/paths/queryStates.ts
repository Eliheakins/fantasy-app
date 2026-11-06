import { EMPTY_QUERY, MAX_PINNED_PLAYERS, type QueryState } from "@/stat/lib/queryUrl";
import { type QueryIntent } from "@/stat/lib/nlqApi";
import { specFromIntent, unsupportedReasons } from "@/stat/lib/querySpec";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import type { Side, Split } from "@/stat/types/queryBuilder";
import type { AnswerPath } from "../interpretQuestion";
import { withDefaultSeasonType } from "../intentFilters";
import { type Leaderboard, splitAsked } from "../ruleParser";
import { settleStats } from "../settleStats";
import type { AskActions } from "./types";

/** "by season" and "each game" split the answer, whichever path read the rest of the question. */
const splitOf = (question: string): Split | null => {
  const split = splitAsked(question);
  return split === "both" ? null : split;
};

/** Answers with the named players and the intent's stats and filters, unless the engine cannot run them. */
export function showIntent(
  players: PlayerDictionaryRow[],
  intent: QueryIntent,
  asked: string,
  path: AnswerPath,
  unrecognized: string[],
  actions: AskActions,
): void {
  const ids = [...new Set(players.map((p) => p.gsis_id))].slice(0, MAX_PINNED_PLAYERS);
  const stats = settleStats(intent.stat_ids, { kind: "players", positions: players.map((p) => p.position) });
  const blocked = unsupportedReasons(specFromIntent({ ...intent, stat_ids: stats }, ids));
  if (blocked.length > 0) {
    actions.fail(asked, path, blocked.join(" "));
    return;
  }
  const next: QueryState = {
    ...EMPTY_QUERY,
    players: ids,
    stats,
    filters: withDefaultSeasonType(intent.filter_ids),
    granularity: intent.granularity,
    minPlays: 0,
    order: null,
    limit: null,
    split: splitOf(asked),
  };
  actions.answer(next, asked, path, unrecognized);
}

/** Answers a league ranking or a team question the rules read with no player to match, so no model call. */
export function showRules(
  intent: QueryIntent,
  board: Leaderboard | undefined,
  team: { ids: string[]; side: Side } | undefined,
  asked: string,
  actions: AskActions,
): void {
  const subject = team ? ({ kind: "team" } as const) : ({ kind: "players", positions: [] } as const);
  const stats = settleStats(intent.stat_ids, subject);
  const order = board ? { ...board.order, metric: settleStats([board.order.metric], subject)[0]! } : null;
  const next: QueryState = {
    ...EMPTY_QUERY,
    subject: team ? "teams" : "players",
    teams: team?.ids ?? [],
    side: team?.side ?? "offense",
    stats,
    filters: withDefaultSeasonType(intent.filter_ids),
    granularity: intent.granularity,
    minPlays: board?.minPlays ?? 0,
    order,
    limit: board?.limit ?? null,
    split: splitOf(asked),
  };
  actions.answer(next, asked, "rules", []);
}
