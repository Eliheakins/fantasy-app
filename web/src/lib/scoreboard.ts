import type { components } from "@/api/schema";
import { formatNumber, formatPercent } from "@/viz";

type Schemas = components["schemas"];
export type ScoreboardRow = Schemas["ScoreboardRow"];
export type ScoreboardSide = Schemas["ScoreboardSide"];

/** The viewed team's side first, so the card reads "you, then them". */
export function orderedSides(row: ScoreboardRow): [ScoreboardSide, ScoreboardSide] {
  return row.b.is_me && !row.a.is_me ? [row.b, row.a] : [row.a, row.b];
}

export const isMine = (row: ScoreboardRow): boolean => row.a.is_me || row.b.is_me;

export function sideName(side: ScoreboardSide): string {
  return side.is_me ? `${side.team_name} (you)` : side.team_name;
}

/** My matchup first, the rest in the order Sleeper gives them; returns a new array. */
export const sortMineFirst = (rows: readonly ScoreboardRow[]): ScoreboardRow[] => [
  ...rows.filter(isMine),
  ...rows.filter((r) => !isMine(r)),
];

export type SideScore = { value: string; unit: "final" | "so far" | "proj"; win: string | null; projected?: string };

/** The number a side shows: final points, points so far plus the projected final, or the projection before kickoff. */
export function sideScore(side: ScoreboardSide, status: ScoreboardRow["status"]): SideScore {
  const win = side.win_prob === null ? null : formatPercent(side.win_prob);
  if (status === "Final") return { value: formatNumber(side.points), unit: "final", win: null };
  if (status === "Live") return { value: formatNumber(side.points), unit: "so far", win, projected: formatNumber(side.projected) };
  return { value: formatNumber(side.projected), unit: "proj", win };
}

/** Earliest timed kickoff of the week, or null. */
export function firstKickoff(kickoffs: readonly { kickoff: string | null }[]): Date | null {
  const times = kickoffs.flatMap((k) => (k.kickoff === null ? [] : [Date.parse(k.kickoff)])).filter(Number.isFinite);
  return times.length ? new Date(Math.min(...times)) : null;
}

/** "Final", "Live", or the week's first kickoff (New York time) for a matchup still to start. */
export function matchupStatus(status: ScoreboardRow["status"], kickoff: Date | null): string {
  if (status !== "Not started" || kickoff === null) return status;
  return kickoff
    .toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", hour: "numeric", minute: "2-digit" })
    .replace(",", "");
}

export const LIVE_NOTE = "Live points are only as fresh as the last refresh; win chances count the points already scored.";
