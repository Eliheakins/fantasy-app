/** Share of paired simulations in which a change helps, bucketed per docs/spec/dashboard.md. */
export type ConfidenceLevel = "clear" | "lean" | "toss-up";
export type DeltaTone = "positive" | "negative" | "neutral";

export const CLEAR_SHARE = 0.7;
export const LEAN_SHARE = 0.55;
/** Monte Carlo noise at 50k runs is about 0.2 points; below this a delta is shown as "~". */
export const NOISE_POINTS = 0.5;

export type FormattedDelta = { text: string; tone: DeltaTone; sign: -1 | 0 | 1 };

/** 0.62 becomes "62%". Missing values become an en dash. */
export function formatPercent(fraction: number | null | undefined): string {
  if (fraction == null || !Number.isFinite(fraction)) return "–";
  return `${Math.round(fraction * 100)}%`;
}

/** One decimal, never "-0.0". */
export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const text = value.toFixed(digits);
  return Number(text) === 0 ? (0).toFixed(digits) : text;
}

/** Points of probability or fantasy score: "+4.1 ▲", "-2.0 ▼", "~0.4" inside the noise band. */
export function formatDelta(points: number, noise: number = NOISE_POINTS): FormattedDelta {
  if (!Number.isFinite(points)) return { text: "–", tone: "neutral", sign: 0 };
  const magnitude = formatNumber(Math.abs(points));
  if (Math.abs(points) < noise) {
    // "~0.5" would read as the threshold itself, so a value that rounds up to it keeps its sign.
    if (Number(magnitude) < noise) return { text: `~${magnitude}`, tone: "neutral", sign: 0 };
    return { text: `${points > 0 ? "+" : "-"}${magnitude}`, tone: "neutral", sign: 0 };
  }
  return points > 0
    ? { text: `+${magnitude} ▲`, tone: "positive", sign: 1 }
    : { text: `-${magnitude} ▼`, tone: "negative", sign: -1 };
}

export function confidenceFromShare(share: number): ConfidenceLevel {
  if (share >= CLEAR_SHARE) return "clear";
  if (share >= LEAN_SHARE) return "lean";
  return "toss-up";
}
