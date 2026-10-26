import type { components } from "@/api/schema";

export type ScorecardData = components["schemas"]["ScorecardData"];
export type ScorecardRow = components["schemas"]["ScorecardRow"];
export type Model = ScorecardRow["model"];

export const MODELS: readonly Model[] = ["learned", "baseline", "sleeper"];
export const MODEL_LABEL: Record<Model, string> = { learned: "Learned", baseline: "Baseline", sleeper: "Sleeper" };
export const ALL_POSITIONS = "ALL";
export const ALL_TIERS = -1;
/** A cell with fewer player-games than this is too noisy to rank models on. */
export const SMALL_N = 30;
export const TIER_LABEL: Record<number, string> = {
  [ALL_TIERS]: "All sizes",
  0: "Low projection third",
  1: "Middle projection third",
  2: "High projection third",
};
const POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF"];

export const EMPTY_TEXT = "Fills after the first archived week finishes and you run make refresh.";

export type Cell = { n: number; mae: number | null; bias: number | null };
export type Line = {
  key: string;
  label: string;
  /** Player-games scored for the learned model (else the baseline), the row's headline count. */
  n: number;
  cells: Partial<Record<Model, Cell>>;
  /** Lowest mean absolute error in the row, only when two or more models have a value. */
  best: Model | null;
  small: boolean;
};

/** Group rows into lines, then pick the model with the lowest MAE per line. */
function toLines(rows: readonly ScorecardRow[], lineKey: (r: ScorecardRow) => { key: string; label: string }): Line[] {
  const byKey = new Map<string, Line>();
  for (const r of rows) {
    const { key, label } = lineKey(r);
    const line = byKey.get(key) ?? { key, label, n: 0, cells: {}, best: null, small: false };
    line.cells[r.model] = { n: r.n, mae: r.mae ?? null, bias: r.bias ?? null };
    byKey.set(key, line);
  }
  return [...byKey.values()].map((line) => {
    const scored = MODELS.filter((m) => line.cells[m]?.mae != null);
    const best = scored.length > 1 ? scored.reduce((a, b) => ((line.cells[b]?.mae ?? 0) < (line.cells[a]?.mae ?? 0) ? b : a)) : null;
    const n = (line.cells.learned ?? line.cells.baseline ?? line.cells.sleeper)?.n ?? 0;
    return { ...line, best, n, small: MODELS.some((m) => (line.cells[m]?.n ?? Infinity) < SMALL_N) };
  });
}

export function weekLines(rows: readonly ScorecardRow[]): Line[] {
  const kept = rows.filter((r) => r.week != null && r.position === ALL_POSITIONS && r.tier === ALL_TIERS);
  return toLines(kept, (r) => ({ key: `w${String(r.week).padStart(2, "0")}`, label: `Week ${r.week}` })).sort((a, b) => a.key.localeCompare(b.key));
}

export function positionLines(rows: readonly ScorecardRow[]): Line[] {
  const kept = rows.filter((r) => r.week == null && r.tier === ALL_TIERS);
  const rank = (p: string) => (p === ALL_POSITIONS ? -1 : POSITION_ORDER.indexOf(p) === -1 ? 99 : POSITION_ORDER.indexOf(p));
  return toLines(kept, (r) => ({ key: r.position, label: r.position === ALL_POSITIONS ? "All positions" : r.position })).sort((a, b) => rank(a.key) - rank(b.key));
}

export function tierLines(rows: readonly ScorecardRow[]): Line[] {
  const kept = rows.filter((r) => r.week == null && r.position === ALL_POSITIONS);
  const tier = (r: ScorecardRow) => ({ key: String(r.tier), label: TIER_LABEL[r.tier] ?? `Tier ${r.tier}` });
  return toLines(kept, tier).sort((a, b) => Number(a.key) - Number(b.key));
}

export function weeksText(weeks: readonly number[]): string {
  if (weeks.length === 0) return "none";
  return weeks.length === 1 ? `week ${weeks[0]}` : `weeks ${weeks.join(", ")}`;
}

export function leftOutText(e: ScorecardData["excluded"]): string {
  const parts = [
    [e.not_final, "not final yet"],
    [e.no_kickoff, "no kickoff time"],
    [e.no_snapshot, "no snapshot fetched before kickoff"],
  ] as const;
  const shown = parts.filter(([n]) => n > 0).map(([n, why]) => `${n} ${why}`);
  return shown.length ? `Left out: ${shown.join("; ")}.` : "Nothing was left out.";
}
