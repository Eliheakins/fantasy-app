import type { OutlookRow } from "@/features/outlook/types";

export const PAGE_SIZE = 25;
export const ALL_POSITIONS = "ALL";
const POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF"];

/** Biggest projected gain first; players with no change figure last. Returns a new array. */
export function sortByChange(rows: readonly OutlookRow[]): OutlookRow[] {
  const key = (r: OutlookRow) => (r.change == null || Number.isNaN(r.change) ? Number.NEGATIVE_INFINITY : r.change);
  return [...rows].sort((a, b) => key(b) - key(a));
}

/** Positions present in the rows, in the usual order, after "All". */
export function positionsIn(rows: readonly OutlookRow[]): string[] {
  const present = new Set(rows.map((r) => r.position));
  const known = POSITION_ORDER.filter((p) => present.has(p));
  const other = [...present].filter((p) => !POSITION_ORDER.includes(p)).sort();
  return [ALL_POSITIONS, ...known, ...other];
}

export function filterByPosition(rows: readonly OutlookRow[], position: string): OutlookRow[] {
  return position === ALL_POSITIONS ? [...rows] : rows.filter((r) => r.position === position);
}

/** A player who will not play this game has no change worth acting on: show it neutral. */
export function isOut(row: OutlookRow): boolean {
  return row.chance_to_play === 0;
}
