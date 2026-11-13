import type { components } from "@/api/schema";
import { confidenceFromShare, formatNumber, formatPercent } from "@/viz";
import { isMine, orderedSides, type ScoreboardRow } from "@/lib/scoreboard";
import { type LineupRow, type ObjectiveKey, type WinProbability, slotLabel } from "./logic";

export type SlotCall = components["schemas"]["SlotCall"];

/** The simulation's option name for each objective the switch offers. */
export const OPTION_OF: Record<ObjectiveKey, string> = {
  expected_points: "max_points",
  win_probability: "win_prob",
  max_ceiling: "ceiling",
  max_floor: "floor",
};

/** Per-slot paired shares for the lineup an objective shows; empty before the simulation finishes. */
export function slotCalls(odds: WinProbability | null, objective: ObjectiveKey): readonly SlotCall[] {
  return odds?.options.find((o) => o.option === OPTION_OF[objective])?.slot_calls ?? [];
}

/** How often the side that scores more does, 0.5 to 1. */
export const winnerShare = (call: SlotCall): number => Math.max(call.share ?? 0.5, 1 - (call.share ?? 0.5));

/**
 * Close calls are slots where the starter is not clearly better; clear slots collapse into one line.
 * A locked starter is settled, so it is in neither list.
 */
export function splitCalls(calls: readonly SlotCall[], locked: ReadonlySet<string>) {
  const open = calls.filter((c) => !locked.has(c.starter));
  const isClose = (c: SlotCall) => c.share !== null && confidenceFromShare(c.share) !== "clear";
  return { close: open.filter(isClose), clear: open.filter((c) => !isClose(c)) };
}

/** What the objective is chasing, for the "over" part of a call whose starter scores less often. */
export const REASON_OF: Partial<Record<ObjectiveKey, string>> = {
  max_ceiling: "upside",
  max_floor: "floor",
  win_probability: "win chance",
};

export function callText(call: SlotCall, names: Readonly<Record<string, string>>, reason?: string): string {
  const [starter, alt] = [names[call.starter] ?? call.starter, names[call.alternative ?? ""] ?? call.alternative];
  const slot = slotLabel(call.slot);
  if (call.share === null) return `${slot}: ${starter}, nobody eligible on the bench`;
  if (call.share >= 0.5) return `${slot}: ${starter} over ${alt}, better in ${formatPercent(call.share)} of simulations`;
  const why = reason ? ` for the ${reason}` : "";
  return `${slot}: ${starter} over ${alt}${why}; ${alt} scores more in ${formatPercent(1 - call.share)} of simulations`;
}

/** "If Cook is out: start Bernard" for each starter the API gave a fallback. */
export function scratchFallbacks(rows: readonly LineupRow[]) {
  return rows
    .filter((r) => r.recommended && r.swap_in)
    .map((r) => ({ gsisId: r.gsis_id, text: `If ${r.full_name} is out: start ${r.swap_in}` }));
}

/** Always win probability: it already takes variance as the underdog and protects the floor as the
 * favourite, and no ceiling or floor lineup beat it on win probability (decisions, 2026-10-23). */
export const RECOMMENDED_OBJECTIVE: ObjectiveKey = "win_probability";

const MAX_NAMED_STARTS = 2;

/** The page's h1: who to start, or that nothing needs changing. */
export function startAnswer(rows: readonly LineupRow[], sleeperKnown: boolean): string {
  if (!sleeperKnown) return "Your best lineup";
  const starts = rows.filter((r) => r.recommended && r.change === "Start");
  if (starts.length === 0) return "Your lineup is set";
  if (starts.length > MAX_NAMED_STARTS) return `Make ${starts.length} lineup changes`;
  return `Start ${starts.map((r) => `${r.full_name} at ${slotLabel(r.slot)}`).join(", ")}`;
}

export type WeekResult = { me: number; them: number; outcome: "won" | "lost" | "tied" };

/** My final score, the opponent's and the outcome once my matchup is final; null while any game is left. */
export function weekResult(board: readonly ScoreboardRow[] | null): WeekResult | null {
  const row = board?.find(isMine);
  if (!row || row.status !== "Final") return null;
  const [me, them] = orderedSides(row);
  const outcome = me.points > them.points ? "won" : me.points < them.points ? "lost" : "tied";
  return { me: me.points, them: them.points, outcome };
}

/** "Week 8 is over: won 127.9 to 107.5" once my matchup is final; null while any game is left. */
export function weekOverText(week: number, board: readonly ScoreboardRow[] | null): string | null {
  const r = weekResult(board);
  return r && `Week ${week} is over: ${r.outcome} ${formatNumber(r.me)} to ${formatNumber(r.them)}`;
}

/** "Won by 20.4", "Lost by 11.5" or "Tied". */
export function resultText(r: WeekResult): string {
  if (r.outcome === "tied") return "Tied";
  return `${r.outcome === "won" ? "Won" : "Lost"} by ${formatNumber(Math.abs(r.me - r.them))}`;
}
