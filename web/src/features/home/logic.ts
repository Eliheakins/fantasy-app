import type { components } from "@/api/schema";
import type { League } from "@/api/types";
import type { TeamRow } from "@/lib/teamContext";
import { formatNumber, formatPercent } from "@/viz";

type Schemas = components["schemas"];
export type SeasonOdds = Schemas["SeasonOddsRow"];
export type LiveScore = Schemas["LiveScoreRow"];
export type RosterRow = Schemas["RosterRow"];
export type ActionRow = Schemas["ActionRow"];
export type WinProbability = Schemas["WinProbabilityData"];
export type Unmatched = Schemas["UnmatchedData"];

/** "Colgate 5-2 · 801.3 PF · week 7": same fallbacks as app/Home.py. */
export function recordLine(l: League): string {
  const record = l.wins == null || l.losses == null ? "no record yet" : l.record;
  const pf = l.points_for == null ? "no" : l.points_for.toFixed(1);
  const week = l.current_week == null ? "unknown" : l.current_week;
  return `${record} · ${pf} PF · week ${week}`;
}

/** The league card for the team being viewed: its name and record in place of mine. */
export function asViewedTeam(l: League, viewed: TeamRow | null): League {
  if (viewed === null) return l;
  const { team_name, wins, losses, ties, points_for, record } = viewed;
  return { ...l, team_name, wins, losses, ties, points_for, record };
}

/** Streamlit shows playoffs and bye as whole percents, the title to one decimal. */
export function titlePercent(fraction: number | null | undefined): string {
  return fraction == null ? "–" : `${(fraction * 100).toFixed(1)}%`;
}

export function myOdds(rows: readonly SeasonOdds[]): SeasonOdds | null {
  return rows.find((r) => r.is_me) ?? null;
}

export function winChance(data: WinProbability): number | null {
  return data.options.find((o) => o.option === "max_points")?.win_prob ?? null;
}

/** Team-total range of my max-points lineup (held-out p10, median, p90). */
export function myRange(data: WinProbability) {
  const o = data.options.find((x) => x.option === "max_points");
  return o ? { p10: o.floor, p50: o.median, p90: o.ceiling } : null;
}

/** Opponent team-total range; the same on every option row, so read the max-points one. */
export function opponentRange(data: WinProbability) {
  const o = data.options.find((x) => x.option === "max_points");
  return o ? { p10: o.opp_floor, p50: o.opp_median, p90: o.opp_ceiling } : null;
}

const POINTS_IN_TEXT = /([+-]\d+(?:\.\d+)?) points/;

/** The action text carries its gain ("+4.1 points"); there is no separate field yet. */
export function actionPoints(text: string): number | null {
  const m = POINTS_IN_TEXT.exec(text);
  return m ? Number(m[1]) : null;
}

/** Only the win-probability action has a measured share of simulations that favour it. */
export function actionShare(action: ActionRow, data: WinProbability | null): number | null {
  if (action.kind !== "Win probability" || data === null) return null;
  return data.options.find((o) => o.option === "win_prob")?.share_better ?? null;
}

export const liveScoreText = (r: LiveScore) =>
  `${formatNumber(r.points)} (projected final ${r.projected_final.toFixed(0)})`;
export { formatPercent };
