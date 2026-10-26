import type { components } from "@/api/schema";
import { formatNumber, sharedDomain } from "@/viz";

type Schemas = components["schemas"];
export type LineupRow = Schemas["LineupRow"];
export type WinProbability = Schemas["WinProbabilityData"];
export type ComparisonRow = Schemas["ComparisonRow"];
export type Summary = Schemas["SummaryModel"];

export const OBJECTIVES = [
  { key: "expected_points", label: "Expected points" },
  { key: "win_probability", label: "Win probability" },
  { key: "max_ceiling", label: "Max ceiling" },
  { key: "max_floor", label: "Max floor" },
] as const;
export type ObjectiveKey = (typeof OBJECTIVES)[number]["key"];

export const LAST_WEEK = 18;

/** Rows for an objective; the lineup route's own rows when the simulation has not produced them. */
export function rowsFor(
  base: readonly LineupRow[],
  odds: WinProbability | null,
  objective: ObjectiveKey,
): readonly LineupRow[] {
  const reslotted = odds?.lineups[objective];
  return reslotted && reslotted.length > 0 ? reslotted : base;
}

export function splitLineup(rows: readonly LineupRow[]) {
  return {
    start: rows.filter((r) => r.recommended),
    bench: rows.filter((r) => !r.recommended),
  };
}

/** Sleeper lineups are only known when at least one row is marked as started now. */
export function sleeperKnown(rows: readonly LineupRow[]): boolean {
  return rows.some((r) => r.starting_now);
}

export function sumProjection(rows: readonly LineupRow[]): number {
  return rows.reduce((total, r) => total + r.projection, 0);
}

/** Header numbers; computed from the rows so they work before the simulation has finished. */
export function headline(rows: readonly LineupRow[], summary: Summary | undefined) {
  if (summary) {
    return { shown: summary.shown_points, now: summary.sleeper_points, gap: summary.gap, win: summary.win_prob };
  }
  const shown = sumProjection(rows.filter((r) => r.recommended));
  if (!sleeperKnown(rows)) return { shown, now: null, gap: null, win: null };
  const now = sumProjection(rows.filter((r) => r.starting_now));
  return { shown, now, gap: now - shown, win: null };
}

export type ComparisonGroup = { labels: string[]; row: ComparisonRow };

const SAME_KEYS = ["win_prob", "expected_points", "floor", "median", "ceiling"] as const;

/** Options with identical numbers (same lineup) become one row. */
export function collapseComparison(rows: readonly ComparisonRow[]): ComparisonGroup[] {
  const groups: ComparisonGroup[] = [];
  for (const row of rows) {
    const twin = groups.find((g) => SAME_KEYS.every((k) => g.row[k] === row[k]));
    if (twin) twin.labels.push(row.option);
    else groups.push({ labels: [row.option], row });
  }
  return groups;
}

/** The one line shown when rows were merged; null when nothing was. */
export function collapsedNote(groups: readonly ComparisonGroup[]): string | null {
  const merged = groups.filter((g) => g.labels.length > 1);
  if (merged.length === 0) return null;
  return merged.map((g) => `${joinLabels(g.labels)} pick the same lineup, so they share one row.`).join(" ");
}

function joinLabels(labels: readonly string[]): string {
  return labels.length === 2 ? `${labels[0]} and ${labels[1]}` : `${labels.slice(0, -1).join(", ")} and ${labels.at(-1)}`;
}

/** Injury text for a row: the note when the API has one, else the raw status. */
export function injuryLabel(row: Pick<LineupRow, "injury" | "injury_note">): string | null {
  const text = row.injury_note || row.injury;
  return text ? text : null;
}

export function rangeText(row: Pick<LineupRow, "p10" | "p90">): string {
  if (row.p10 == null || row.p90 == null) return "–";
  return `${formatNumber(row.p10)} to ${formatNumber(row.p90)}`;
}

export function tableDomain(rows: readonly LineupRow[]) {
  return sharedDomain(rows.map((r) => ({ p10: r.p10, p50: r.projection, p90: r.p90 })));
}

export const CAVEAT_BASE =
  "Best lineup by projected points for skill positions; K and DEF are not handled yet, and " +
  "players on bye are left out. Players whose game has started are locked in place: locked " +
  "starters stay, locked bench players are not recommended. A game counts as over 200 " +
  "minutes after kickoff, and points are as fresh as the last refresh. The " +
  "status column shows the chance of playing this game and the next, measured from injury " +
  "reports in past seasons (hamstrings and feet linger, a Questionable " +
  "player who did not practice rarely plays), and players who play through an injury are " +
  "discounted a little. The range " +
  "is where about 80 percent of outcomes have landed for players like this. In the win " +
  "probability, the opponent plays the lineup set in Sleeper and K and DEF are league averages.";
export const CAVEAT_UNKNOWN = " Sleeper lineups are only known for the current week.";

export const COMPARISON_CAPTION =
  "Team score including points already scored and K and DEF. Floor and ceiling are the " +
  "10th and 90th percentiles. Win probability, ceiling and floor lineups are chosen on " +
  "half the simulated games and scored on the other half.";

export const NO_SWAP_TEXT =
  "No lineup change is recommended: one flex slot is a small part " +
  "of a team score that spreads about 30 points, so trading expected points for " +
  "upside rarely pays.";

const SLOT_LABELS: Record<string, string> = { SUPER_FLEX: "Superflex", FLEX: "Flex", BN: "Bench" };
const FLEX_SLOTS = new Set(["SUPER_FLEX", "FLEX", "BN"]);

/** Readable slot name: "SUPER_FLEX" becomes "Superflex". */
export const slotLabel = (slot: string): string => SLOT_LABELS[slot] ?? slot;
/** The position is only news when the slot does not already say it. */
export const slotHidesPosition = (slot: string): boolean => FLEX_SLOTS.has(slot);

/** True when the four objectives would play different lineups, so the picker means something. */
export const lineupsDiffer = (rows: readonly ComparisonRow[]): boolean => collapseComparison(rows).length > 1;

const NOISE_GAP_POINTS = 0.5;
/** A gap this small is the same lineup as far as the simulation can tell. */
export const gapIsNoise = (gap: number): boolean => Math.abs(gap) < NOISE_GAP_POINTS;

/** "–" for a game that has not produced points, else the points. */
export function pointsSoFar(row: Pick<LineupRow, "actual" | "locked">): string {
  return row.actual === 0 && !row.locked ? "–" : formatNumber(row.actual);
}

const MIN_SPREAD_POINTS = 0.05;
/** A range with no spread is a finished game or a player with no outlook (out, bye): no bar. */
export const hasRange = (row: Pick<LineupRow, "p10" | "p90">): boolean =>
  row.p10 != null && row.p90 != null && row.p90 > 0 && row.p90 - row.p10 >= MIN_SPREAD_POINTS;
