import { scaleLinear } from "d3-scale";

export type Range = { p10?: number | null; p50?: number | null; p90?: number | null };
export type Domain = readonly [number, number];
export type BarLayout = {
  /** Pixel x of the bar ends, or null when an end is missing (tick-only). */
  bar: { x1: number; x2: number } | null;
  tick: number | null;
};

const AXIS_PAD = 0.05;

function finite(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** One axis for a whole table so bar lengths compare. Null when no row has a number. */
export function sharedDomain(rows: readonly Range[]): Domain | null {
  const values = rows.flatMap((r) => [r.p10, r.p50, r.p90]).filter(finite);
  if (values.length === 0) return null;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const pad = (high - low) * AXIS_PAD || 1;
  return [low - pad, high + pad];
}

/** Pixel layout on a shared domain. Values outside the domain clamp to its edges. */
export function layoutRange(range: Range, domain: Domain, width: number): BarLayout {
  const x = scaleLinear().domain([...domain]).range([0, width]).clamp(true);
  const tick = finite(range.p50) ? x(range.p50) : null;
  if (!finite(range.p10) || !finite(range.p90)) return { bar: null, tick };
  const [lo, hi] = [x(Math.min(range.p10, range.p90)), x(Math.max(range.p10, range.p90))];
  return { bar: { x1: lo, x2: hi }, tick };
}

export function rangeLabel(range: Range): string {
  const one = (v: number) => v.toFixed(1);
  if (!finite(range.p50) && !finite(range.p10) && !finite(range.p90)) return "No projection";
  const median = finite(range.p50) ? `Median ${one(range.p50)}` : "No median";
  if (!finite(range.p10) || !finite(range.p90)) return `${median}, range unavailable`;
  const [lo, hi] = [Math.min(range.p10, range.p90), Math.max(range.p10, range.p90)];
  return `${median}, range ${one(lo)} to ${one(hi)}`;
}
