import { formatNumber } from "@/viz";
import type { components } from "@/api/schema";

export type WaiverRow = components["schemas"]["WaiverRow"];
export type StrengthRow = components["schemas"]["StrengthRow"];
export type StreamerRow = components["schemas"]["StreamerRow"];
export type PlayerWeekRow = components["schemas"]["PlayerWeekRow"];

export type ChangeKind = "missing" | "noise" | "delta";
export type Change = { kind: ChangeKind; points: number; noiseText: string };

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

export const STRENGTH_CAPTION =
  "Your best lineup each week against the stand-in free agent at each position (the third-best or so on the wire, since the top ones are the adds). Rank 1 is the strongest team. Thin positions are where an add helps; deep ones are where a trade can come from.";
export const ADDS_CAPTION =
  "Free agents ranked by expected points over the rest of the season above what you would have anyway. Every slot can always be filled by a stand-in free agent (bye weeks, injuries and weak starters included), so a backup at a position with plenty of free agents adds almost nothing, and the drop is whoever costs least. Playoff and title changes re-run the season simulation with the move made, on the same random draws as the unchanged roster. The title change carries a Monte Carlo error of up to the value in the last column, so title changes smaller than that are noise. Injured players are scaled by their status.";
export const TRENDING_CAPTION =
  "Sleeper adds is how many users added the player in the latest trending pull, a rough sign of who else will bid. Select a row to see the next four weeks.";
export const STREAM_CAPTION =
  "Projected points over the next three weeks (a bye week counts as zero). The projection is recent form plus the game's implied total, and beats a plain league average only slightly for defenses (about 3% lower error) and not at all for kickers, so treat small gaps as noise. Your own player is marked.";
