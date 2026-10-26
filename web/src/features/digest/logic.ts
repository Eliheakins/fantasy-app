import { formatNumber } from "@/viz";
import type { ActionRow, IdeasInfo, LastWeekRow, OddsChangeRow, ProjectionMissRow } from "./types";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? "" : "s"} ago`;
}

/** "4 hours ago"; a time slightly in the future or under a minute old reads "just now". */
export function formatAge(iso: string, nowMs: number): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "unknown age";
  const age = nowMs - then;
  if (age < MINUTE_MS) return "just now";
  if (age < HOUR_MS) return plural(Math.floor(age / MINUTE_MS), "minute");
  if (age < DAY_MS) return plural(Math.floor(age / HOUR_MS), "hour");
  return plural(Math.floor(age / DAY_MS), "day");
}

/** A probability change as percentage points; null stays null (no earlier run is not zero). */
export function toPoints(fraction: number | null): number | null {
  return fraction === null ? null : fraction * 100;
}

export function maxAbsDiff(rows: readonly Pick<ProjectionMissRow, "diff">[]): number {
  return rows.reduce((m, r) => (r.diff === null ? m : Math.max(m, Math.abs(r.diff))), 0);
}

/** Bar from the centre line: right for points above projection, left for below. `half` is the width either side. */
export function barSpan(diff: number | null, max: number, half: number): { x: number; width: number } | null {
  if (diff === null || max <= 0) return null;
  const width = Math.min(Math.abs(diff) / max, 1) * half;
  return { x: diff >= 0 ? half : half - width, width };
}

const VERB = { W: "Won", L: "Lost", T: "Tied" } as const;

export function resultSentence(r: Pick<LastWeekRow, "result" | "points" | "opp_points" | "opponent">): string {
  const against = r.opponent ? ` against ${r.opponent}` : "";
  return `${VERB[r.result]} ${formatNumber(r.points)} to ${formatNumber(r.opp_points)}${against}`;
}

/** The weeks the odds change compares; previous is null when there is no earlier run. */
export function oddsComparison(rows: readonly OddsChangeRow[]): { latest: number; previous: number | null } | null {
  const first = rows[0];
  return first ? { latest: first.as_of_week, previous: first.prev_as_of_week } : null;
}

/** Why a kind of idea cannot be shown (or is old), else null. */
export function ideasNotice(info: IdeasInfo, kind: "waiver" | "trade"): string | null {
  if (!info.is_mine) {
    return "Ideas are generated only for the team that is yours in Sleeper. Switch the team selector back to see them.";
  }
  if (info.created_at === null) {
    return "No ideas stored yet. Run make refresh; the digest step saves them.";
  }
  if (kind === "trade" && info.deadline_passed) {
    return `The trade deadline (week ${info.trade_deadline}) has passed, so there are no trade ideas.`;
  }
  if (info.as_of_week !== null && info.current_week !== null && info.as_of_week < info.current_week) {
    return `These ideas are from week ${info.as_of_week}; it is now week ${info.current_week}. Run make refresh for new ones.`;
  }
  return null;
}

/** The first action that is about the lineup; waiver adds have their own section. */
export function nextLineupAction(actions: readonly ActionRow[]): ActionRow | null {
  return actions.find((a) => a.kind !== "Waiver") ?? null;
}
