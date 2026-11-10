import { formatNumber, toPoints } from "@/viz";

type ChangeKind = "missing" | "noise" | "delta";
type Change = { kind: ChangeKind; points: number; noiseText: string };

/** Probability change in percentage points; a change inside the Monte Carlo error is noise ("~"). */
export function classifyChange(change: number | null, error: number | null = null): Change {
  if (change == null || !Number.isFinite(change)) return { kind: "missing", points: 0, noiseText: "–" };
  const points = toPoints(change);
  if (error != null && Math.abs(change) <= error) {
    return { kind: "noise", points, noiseText: `~${formatNumber(Math.abs(points))}` };
  }
  return { kind: "delta", points, noiseText: "" };
}
