import type { components } from "@/api/schema";
import type { League } from "@/api/types";
import type { TeamRow } from "@/lib/teamContext";
import { confidenceFromShare, formatNumber, formatPercent } from "@/viz";

type Schemas = components["schemas"];
export type SeasonOdds = Schemas["SeasonOddsRow"];
export type LiveScore = Schemas["LiveScoreRow"];
export type RosterRow = Schemas["RosterRow"];
export type ActionRow = Schemas["ActionRow"];
export type WinProbability = Schemas["WinProbabilityData"];
export type Unmatched = Schemas["UnmatchedData"];

/** "Colgate 5-2 · 801.3 PF · week 7": with fallbacks for missing fields. */
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

const DECIMAL_BELOW = 0.1;

/** One rule for every season odd: whole percents, one decimal under 10% so small odds do not read as 0. */
export function oddsPercent(fraction: number | null | undefined): string {
  if (fraction == null) return "–";
  return fraction < DECIMAL_BELOW ? `${(fraction * 100).toFixed(1)}%` : formatPercent(fraction);
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

/** Points so far and projected final as separate pieces, so a line never breaks inside a number. */
export const liveScoreParts = (r: LiveScore) => ({
  so_far: formatNumber(r.points),
  projected: formatNumber(r.projected_final, 0),
});

/** Below these an action is inside the noise: it is not worth a move. */
const MIN_WIN_EDGE_POINTS = 0.5;
const MIN_ACTION_POINTS = 0.5;

const CONFIDENCE_PREFIX = /^(clear|lean|toss-up):\s*/i;
const POINTS_SUFFIX = /,?\s*\(?[+-]\d+(?:\.\d+)?\s*points\)?/;
const WIN_PAIR = /\((\d+(?:\.\d+)?)% vs (\d+(?:\.\d+)?)% to win\)/;

/** The action sentence without the confidence word and the point gain, which are shown beside it. */
export function actionSentence(text: string): string {
  return text.replace(CONFIDENCE_PREFIX, "").replace(POINTS_SUFFIX, "").trim();
}

/** Gain in points: the structured field, else read out of the text. */
export function actionGain(a: ActionRow): number | null {
  return a.delta_points ?? actionPoints(a.text);
}

/** Percentage-point edge in "(98.6% vs 98.3% to win)", or null when the text has none. */
function winEdge(text: string): number | null {
  const m = WIN_PAIR.exec(text);
  return m ? Number(m[1]) - Number(m[2]) : null;
}

/** Drops actions whose edge is inside the noise band or whose confidence is a toss-up. */
export function worthActing(a: ActionRow, share: number | null): boolean {
  if (share !== null && confidenceFromShare(share) === "toss-up") return false;
  const edge = winEdge(a.text);
  if (edge !== null && Math.abs(edge) < MIN_WIN_EDGE_POINTS) return false;
  const gain = actionGain(a);
  return gain === null || edge !== null || Math.abs(gain) >= MIN_ACTION_POINTS;
}

export function splitRoster(rows: readonly RosterRow[]) {
  return { starters: rows.filter((r) => r.is_starter), bench: rows.filter((r) => !r.is_starter) };
}
;
