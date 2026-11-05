/**
 * Display formatting for query result cell values (shared across Explore and Ask).
 */
export function formatQueryValue(v: unknown): string {
  if (v === null || v === undefined) {
    return "—";
  }
  if (typeof v === "number" && !Number.isInteger(v)) {
    // Per-game and per-play values carry no more precision than the data supports: one decimal from 10 up, two from 1, three below.
    const abs = Math.abs(v);
    return v.toFixed(abs >= 10 ? 1 : abs >= 1 ? 2 : 3);
  }
  return String(v);
}
