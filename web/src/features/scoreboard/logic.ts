import type { components } from "@/api/schema";
import { formatNumber, formatPercent, sharedDomain } from "@/viz";
import type { Domain } from "@/viz/rangeAxis";

type Schemas = components["schemas"];
export type ScoreboardRow = Schemas["ScoreboardRow"];
export type ScoreboardSide = Schemas["ScoreboardSide"];

export const FIRST_WEEK = 1;
export const LAST_WEEK = 18;

export const clampWeek = (week: number): number => Math.min(Math.max(week, FIRST_WEEK), LAST_WEEK);

/** The viewed team's side first, so the card reads "you, then them". */
export function orderedSides(row: ScoreboardRow): [ScoreboardSide, ScoreboardSide] {
  return row.b.is_me && !row.a.is_me ? [row.b, row.a] : [row.a, row.b];
}

export const isMine = (row: ScoreboardRow): boolean => row.a.is_me || row.b.is_me;

/** One axis for the two sides of a matchup, so bar lengths compare. */
export function cardDomain(row: ScoreboardRow): Domain | null {
  return sharedDomain([row.a, row.b].map((s) => ({ p10: s.floor, p50: s.median, p90: s.ceiling })));
}

export function sideName(side: ScoreboardSide): string {
  return side.is_me ? `${side.team_name} (you)` : side.team_name;
}

/** What a side has so far, by the state of its matchup. */
export function pointsLine(side: ScoreboardSide, status: ScoreboardRow["status"]): string {
  if (status === "Not started") return "Not started";
  if (status === "Final") return `${formatNumber(side.points)} pts final`;
  return `${formatNumber(side.points)} pts so far, ${formatPercent(side.share_left)} of games left`;
}

export function rangeText(side: ScoreboardSide): string {
  return `${formatNumber(side.floor)} to ${formatNumber(side.ceiling)}`;
}

/** The matchup's title for assistive tech, e.g. "Mine versus Theirs". */
export function matchupTitle(row: ScoreboardRow): string {
  const [first, second] = orderedSides(row);
  return `${sideName(first)} versus ${sideName(second)}`;
}

export function winLabel(first: ScoreboardSide, second: ScoreboardSide): string | null {
  if (first.win_prob === null || second.win_prob === null) return null;
  return `Chance to win: ${first.team_name} ${formatPercent(first.win_prob)}, ${second.team_name} ${formatPercent(second.win_prob)}`;
}

export const EMPTY_WEEK = (week: number) =>
  `No matchups are set for week ${week} yet. Sleeper fills in playoff pairings as the season goes on.`;

export const LIVE_NOTE =
  "Live points are only as fresh as the last refresh; win chances count the points already scored.";

/** "Week 7: live" / "Week 7: final" / mixed weeks name each state once. */
export function weekStatus(rows: readonly ScoreboardRow[]): string {
  const states = [...new Set(rows.map((r) => r.status.toLowerCase()))];
  return states.join(", ");
}
export const hasMixedStatus = (rows: readonly ScoreboardRow[]): boolean => new Set(rows.map((r) => r.status)).size > 1;
export const RANGE_LEGEND = "Bars: projected final score, 10 to 90% range, with the median marked.";
