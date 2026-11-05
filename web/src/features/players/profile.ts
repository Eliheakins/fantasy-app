import type { components } from "@/api/schema";
import { formatNumber, formatPercent } from "@/viz";

export type PlayerProfile = components["schemas"]["PlayerProfile"];
type RoleWeek = components["schemas"]["RoleWeek"];

export const MAX_COMPARE = 3;
const SHARED_KEYS = ["league", "team", "week"];

/** The one sentence under the h1: the next game's median and range, else rest of season over replacement. */
export function answerSentence(p: PlayerProfile): string | null {
  if (p.median != null && p.p10 != null && p.p90 != null) {
    const range = `Median ${formatNumber(p.median)} points in week ${p.week}, likely between ${formatNumber(p.p10)} and ${formatNumber(p.p90)}.`;
    return p.chance_to_play != null && p.chance_to_play < 1 ? `${range} ${formatPercent(p.chance_to_play)} to play.` : range;
  }
  if (p.ros_over_replacement != null && p.replacement_name) {
    const gap = p.ros_over_replacement;
    return `${gap >= 0 ? "+" : ""}${formatNumber(gap)} points ${gap >= 0 ? "over" : "against"} ${p.replacement_name} for the rest of the season.`;
  }
  return null;
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
