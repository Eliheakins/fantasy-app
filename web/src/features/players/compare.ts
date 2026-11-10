import { formatNumber } from "@/viz";
import type { PlayerProfile } from "./profile";

type Maybe = number | null | undefined;

const isNumber = (v: Maybe): v is number => typeof v === "number" && Number.isFinite(v);

/** Positions in `values` holding the highest number, when at least two players have one and they differ. */
export function bestIndexes(values: readonly Maybe[]): Set<number> {
  const present = values.flatMap((v, i) => (isNumber(v) ? [{ v, i }] : []));
  if (present.length < 2) return new Set();
  const top = Math.max(...present.map((p) => p.v));
  if (present.every((p) => p.v === top)) return new Set();
  return new Set(present.filter((p) => p.v === top).map((p) => p.i));
}

/** The leader on one measure and its margin over the runner-up; null when fewer than two have a number or it is a tie. */
function lead(values: readonly Maybe[]): { index: number; margin: number } | null {
  const present = values.flatMap((v, i) => (isNumber(v) ? [{ v, i }] : [])).sort((a, b) => b.v - a.v);
  const [first, second] = present;
  return first && second && first.v > second.v ? { index: first.i, margin: first.v - second.v } : null;
}

const signed = (n: number) => `${n >= 0 ? "+" : ""}${formatNumber(n)}`;

/** One sentence on who projects higher next game and for the rest of season, e.g. "Nico Collins projects +2.2 next game and +17.8 rest of season over DJ Moore." */
export function compareVerdict(names: readonly string[], profiles: readonly PlayerProfile[]): string | null {
  const next = lead(profiles.map((p) => p.median));
  const season = lead(profiles.map((p) => p.ros_points));
  const over = (index: number) => (names.length === 2 ? ` over ${names[1 - index]}` : " over the next best");
  if (next && season && next.index === season.index) {
    return `${names[next.index]} projects ${signed(next.margin)} next game and ${signed(season.margin)} rest of season${over(next.index)}.`;
  }
  const parts = [
    next && `${names[next.index]} projects ${signed(next.margin)} next game${over(next.index)}`,
    season && `${names[season.index]} projects ${signed(season.margin)} rest of season${over(season.index)}`,
  ].filter(Boolean);
  return parts.length > 0 ? `${parts.join("; ")}.` : null;
}
