import type { components } from "@/api/schema";
import { MIN_PLAYOFF_GAIN, effectOf, rankTodos, type Effect } from "@/features/effects/effect";
import { type EffectWhy, tradeWhy, waiverWhy } from "@/features/effects/explain";
import type { Phase } from "@/features/effects/phase";

type Waiver = components["schemas"]["WaiverRow"];
type Idea = components["schemas"]["MoveIdeaRow"];

const PERCENT = 100;
const NONE_WORTH_IT = "No move is worth it this week";

export type MoveView = "all" | "fa" | "trades";
export type Move = {
  id: string;
  kind: "add" | "trade";
  title: string;
  detail: string;
  effect: Effect;
  why?: EffectWhy;
  /** The player an add picks up, for a link to his page; null for a trade. */
  player: { gsisId: string; name: string; position: string } | null;
  /** Sleeper trending adds across all Sleeper leagues; shown as a count, not a chance of losing the claim. */
  trendingAdds: number | null;
  /** The player an add drops. Points are net of the drop: the response holds no separate cost for him. */
  drop: { name: string; netPoints: number | null } | null;
};

export const waiverMoves = (rows: readonly Waiver[], phase: Phase = "season"): Move[] =>
  rows.map((w) => ({
    id: `add-${w.gsis_id}`,
    kind: "add",
    title: `Add ${w.full_name}, drop ${w.drop_name}`,
    detail: w.position,
    effect: effectOf(w.playoff_delta, w.title_delta, w.delta_points, phase),
    why: waiverWhy(w.full_name, w.drop_name, phase !== "season"),
    player: { gsisId: w.gsis_id, name: w.full_name, position: w.position },
    trendingAdds: w.trending_adds,
    drop: { name: w.drop_name, netPoints: w.delta_points },
  }));

export const tradeMoves = (rows: readonly Idea[], phase: Phase = "season"): Move[] =>
  rows
    .filter((r) => r.kind === "trade")
    .map((r) => ({
      id: `trade-${r.give_ids.join("+")}-${r.get_ids.join("+")}`,
      kind: "trade",
      title: `Trade ${r.give} for ${r.get}`,
      detail: r.partner ? `with ${r.partner}` : "",
      effect: effectOf(r.playoff_delta, r.title_delta, r.delta_points, phase),
      why: tradeWhy(r.give, r.get, phase !== "season"),
      player: null,
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
