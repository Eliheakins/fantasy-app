import type { components } from "@/api/schema";
import { MIN_PLAYOFF_GAIN, rankTodos, type Effect } from "@/features/thisweek/todos";

type Waiver = components["schemas"]["WaiverRow"];
type Idea = components["schemas"]["MoveIdeaRow"];

/**
 * Sleeper trending adds (users who added the player in the latest pull) at or above this read "likely gone".
 * The pull is the top 50 players league-wide: its adds run 17,000 to 684,000 with a median of 38,000 and a
 * third quartile of 75,000, so 75,000 marks the busiest quarter of an already busy list. See docs/decisions.md.
 */
export const LIKELY_GONE_ADDS = 75_000;
const PERCENT = 100;
const NONE_WORTH_IT = "No move is worth it this week";

export type MoveView = "all" | "fa" | "trades";
export type Move = {
  id: string;
  kind: "add" | "trade";
  title: string;
  detail: string;
  effect: Effect;
  /** The player an add picks up, for a link to his page; null for a trade. */
  player: { gsisId: string; name: string; position: string } | null;
  likelyGone: boolean;
  trendingAdds: number | null;
  /** The player an add drops. Points are net of the drop: the response holds no separate cost for him. */
  drop: { name: string; netPoints: number | null } | null;
};

export const isLikelyGone = (trendingAdds: number | null): boolean => trendingAdds !== null && trendingAdds >= LIKELY_GONE_ADDS;

const toPoints = (fraction: number | null): number | null => (fraction === null ? null : fraction * PERCENT);

export const waiverMoves = (rows: readonly Waiver[]): Move[] =>
  rows.map((w) => ({
    id: `add-${w.gsis_id}`,
    kind: "add",
    title: `Add ${w.full_name}, drop ${w.drop_name}`,
    detail: w.position,
    effect: { playoffPoints: toPoints(w.playoff_delta), points: w.delta_points },
    player: { gsisId: w.gsis_id, name: w.full_name, position: w.position },
    likelyGone: isLikelyGone(w.trending_adds),
    trendingAdds: w.trending_adds,
    drop: { name: w.drop_name, netPoints: w.delta_points },
  }));

export const tradeMoves = (rows: readonly Idea[]): Move[] =>
  rows
    .filter((r) => r.kind === "trade")
    .map((r) => ({
      id: `trade-${r.give_ids.join("+")}-${r.get_ids.join("+")}`,
      kind: "trade",
      title: `Trade ${r.give} for ${r.get}`,
      detail: r.partner ? `with ${r.partner}` : "",
      effect: { playoffPoints: toPoints(r.playoff_delta), points: r.delta_points },
      player: null,
      likelyGone: false,
      trendingAdds: null,
      drop: null,
    }));

/** Adds and trades in one order: playoff-odds change first, then points, never converted (same rule as This week). */
export const rankMoves = (moves: readonly Move[]): Move[] => rankTodos(moves);

export const filterMoves = (moves: readonly Move[], view: MoveView): Move[] =>
  moves.filter((m) => view === "all" || (view === "fa") === (m.kind === "add"));

/** Playoff changes under this many points read "~" everywhere on Moves: the same bar as worthMove. */
export const MOVE_NOISE_PERCENT = MIN_PLAYOFF_GAIN * PERCENT;

/** Worth acting on: the playoff-odds change clears the same bar as the Do this now action. */
export const worthMove = (m: Move): boolean => m.effect.playoffPoints !== null && m.effect.playoffPoints >= MOVE_NOISE_PERCENT;

/** `partial`: one source failed, so "none worth it" only covers what loaded. */
export const moveHeadline = (top: Move | undefined, partial = false): string =>
  top && worthMove(top) ? top.title : partial ? "No move is worth it in what loaded" : NONE_WORTH_IT;
