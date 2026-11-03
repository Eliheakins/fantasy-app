/**
 * Display formatting for DuckDB / query result cell values (shared across Explore and Ask).
 */
export function formatQueryValue(v: unknown): string {
  if (v === null || v === undefined) {
    return "—";
  }
  if (typeof v === "number" && !Number.isInteger(v)) {
    return v.toFixed(4);
  }
  return String(v);
}
