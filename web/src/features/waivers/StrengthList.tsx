import { formatNumber } from "@/viz";
import { barShare, rankedStrength, STRENGTH_CAPTION, type StrengthRow } from "./logic";

export function StrengthList({ rows }: { rows: readonly StrengthRow[] }) {
  const sorted = rankedStrength(rows);
  return (
    <div>
      <ol className="space-y-2">
        {sorted.map((r) => (
          <li key={r.position} className="grid grid-cols-[3rem_1fr_auto] items-center gap-3">
            <span className="font-medium">{r.position}</span>
            <span className="h-3 rounded bg-surface" aria-hidden="true">
              <span
                className="block h-3 rounded bg-mark-muted"
                style={{ width: `${barShare(r.vor_per_week, sorted) * 100}%` }}
              />
            </span>
            <span className="text-caption tabular-nums">
              {formatNumber(r.vor_per_week)} pts/wk, rank {r.rank} of {r.teams}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-caption text-muted">{STRENGTH_CAPTION}</p>
    </div>
  );
}
