import { formatNumber } from "@/viz";
import { barShare, rankedStrength, type StrengthRow } from "./logic";

export function StrengthList({ rows }: { rows: readonly StrengthRow[] }) {
  const sorted = rankedStrength(rows);
  return (
    <ol className="max-w-3xl space-y-2">
      {sorted.map((r) => (
        <li key={r.position} className="grid grid-cols-[3rem_1fr_9rem] items-center gap-3 sm:grid-cols-[3rem_1fr_14rem]">
          <span className="font-medium">{r.position}</span>
          <span className="h-3 rounded bg-surface" aria-hidden="true">
            <span className="block h-3 rounded bg-mark-muted" style={{ width: `${barShare(r.vor_per_week, sorted) * 100}%` }} />
          </span>
          <span className="text-caption tabular-nums">
            {r.vor_per_week >= 0 ? "+" : ""}{formatNumber(r.vor_per_week)} pts/week, rank {r.rank} of {r.teams}
          </span>
        </li>
      ))}
    </ol>
  );
}
