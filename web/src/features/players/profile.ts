import type { components } from "@/api/schema";
import { formatNumber, formatPercent } from "@/viz";

export type PlayerProfile = components["schemas"]["PlayerProfile"];
type RoleWeek = components["schemas"]["RoleWeek"];

export const MAX_COMPARE = 3;
const SHARED_KEYS = ["league", "team", "week"];

const pts = formatNumber;
const OUT = (p: PlayerProfile) => (p.is_out ? " He is out, so this is what he is worth if he returns." : "");

/** "Week 8: 17.3 points, final." when the player's game this week is over. */
export function resultSentence(p: PlayerProfile): string | null {
  return p.result_points != null && p.result_week != null ? `Week ${p.result_week}: ${pts(p.result_points)} points, final.` : null;
}

/** The one sentence under the h1: the result if final, the next game's median and range, else rest of season over replacement. */
export function answerSentence(p: PlayerProfile): string | null {
  const result = resultSentence(p);
  if (p.median != null && p.p10 != null && p.p90 != null && p.week != null) {
    const range = `Median ${pts(p.median)} points in week ${p.week}, likely between ${pts(p.p10)} and ${pts(p.p90)}.`;
    const chance = p.chance_to_play != null && p.chance_to_play < 1 ? ` ${formatPercent(p.chance_to_play)} to play.` : "";
    return [result, range + chance].filter(Boolean).join(" ");
  }
  if (result) return result;
  if (p.ros_over_replacement != null && p.replacement_name) {
    const gap = p.ros_over_replacement;
    return `${gap >= 0 ? "+" : ""}${pts(gap)} points ${gap >= 0 ? "over" : "against"} ${p.replacement_name} for the rest of the season.${OUT(p)}`;
  }
  return null;
}

/** Role stats that mean something for a position: no target share for a QB, no snap share for K or DEF. */
export function roleKeysFor(position: string | null): ("snap_share" | "target_share")[] {
  if (position === "K" || position === "DEF") return [];
  return position === "QB" ? ["snap_share"] : ["snap_share", "target_share"];
}

/** Market change over 30 days: the value then must be positive, else the field is not a usable comparison. */
export function marketChange(value: number, trend: number | null): { change: number; percent: number } | null {
  if (trend == null) return null;
  const then = value - trend;
  return then > 0 ? { change: trend, percent: trend / then } : null;
}

/** One role stat by week as percentages, skipping weeks without it. */
export function roleSeries(weeks: readonly RoleWeek[], key: "snap_share" | "target_share"): number[] {
  return weeks.flatMap((w) => (w[key] == null ? [] : [w[key] * 100]));
}

/** The distinct player ids in repeated `p` params, at most three. */
export function parseCompareIds(params: URLSearchParams): string[] {
  return [...new Set(params.getAll("p").filter(Boolean))].slice(0, MAX_COMPARE);
}

export const withPlayer = (ids: readonly string[], id: string): string[] =>
  ids.includes(id) || ids.length >= MAX_COMPARE ? [...ids] : [...ids, id];

export const withoutPlayer = (ids: readonly string[], id: string): string[] => ids.filter((x) => x !== id);

/** /players/compare for these players, keeping the viewed league, team and week of `search`. */
export function compareHref(ids: readonly string[], search: string): string {
  const current = new URLSearchParams(search);
  const query = new URLSearchParams();
  SHARED_KEYS.forEach((k) => {
    const v = current.get(k);
    if (v !== null) query.set(k, v);
  });
  ids.forEach((id) => query.append("p", id));
  const text = query.toString();
  return text ? `/players/compare?${text}` : "/players/compare";
}
