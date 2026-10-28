import { formatNumber } from "@/viz";
import type { components } from "@/api/schema";

export type WaiverRow = components["schemas"]["WaiverRow"];
export type StrengthRow = components["schemas"]["StrengthRow"];
export type StreamerRow = components["schemas"]["StreamerRow"];
export type PlayerWeekRow = components["schemas"]["PlayerWeekRow"];

type ChangeKind = "missing" | "noise" | "delta";
type Change = { kind: ChangeKind; points: number; noiseText: string };

/** Probability change in percentage points; a change inside the Monte Carlo error is noise ("~"). */
export function classifyChange(change: number | null, error: number | null = null): Change {
  if (change == null || !Number.isFinite(change)) return { kind: "missing", points: 0, noiseText: "–" };
  const points = change * 100;
  if (error != null && Math.abs(change) <= error) {
    return { kind: "noise", points, noiseText: `~${formatNumber(Math.abs(points))}` };
  }
  return { kind: "delta", points, noiseText: "" };
}

/** Rank 1 first; ties keep the API order. */
export function rankedStrength(rows: readonly StrengthRow[]): StrengthRow[] {
  return [...rows].sort((a, b) => a.rank - b.rank);
}

/** Bar length as a share of the largest absolute value, never below zero. */
export function barShare(value: number, rows: readonly StrengthRow[]): number {
  const max = Math.max(...rows.map((r) => Math.abs(r.vor_per_week)), 0);
  return max === 0 ? 0 : Math.min(1, Math.abs(value) / max);
}

export const STRENGTH_CAPTION = "Points a week the best lineup gains over a stand-in free agent at each position. Rank 1 is the strongest team.";
export const STRENGTH_METHOD =
  "The stand-in is the third-best or so free agent at the position, since the top ones are the adds. Thin positions are where an add helps; deep ones are where a trade can come from. Bars start at 0 and scale to the biggest position.";
export const ADDS_CAPTION = "Free agents ranked by extra points over the rest of the season. Select a player to see the next four weeks.";
export const ADDS_METHOD =
  "Extra points are the expected points over the rest of the season above what the roster would have anyway. Every slot can always be filled by a stand-in free agent (bye weeks, injuries and weak starters included), so a backup at a position with plenty of free agents adds almost nothing, and the drop is whoever costs least. Playoff and title changes re-run the season simulation with the move made, on the same random draws as the unchanged roster. The title change carries a Monte Carlo error of up to the value in the Title error column, so title changes smaller than that are noise (shown as ~). Injured players are scaled by their status. Sleeper adds is how many users added the player in the latest trending pull, a rough sign of who else will bid. Not every claim goes through: 67 of 105 waiver claims in these two leagues this season succeeded (64%), and the rate did not rise or fall with the player's market value, so no claim chance is shown per player.";
export const STREAM_CAPTION = "Projected points over the next three weeks; a bye week counts as zero. Treat small gaps as noise.";
export const STREAM_METHOD =
  "The projection is a regression on recent form and the game's implied total; kickers also use the spread, home field, the team's recent offense, the kicker's recent kick volume and the opposing defense's points allowed. Against a plain league average it has about 5% to 7% lower error for defenses and about 2% for kickers.";
