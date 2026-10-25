import { WinBar, formatNumber } from "@/viz";
import { COMPARISON_CAPTION, type ComparisonRow, collapseComparison, collapsedNote } from "./logic";

export function Comparison({ rows }: { rows: readonly ComparisonRow[] }) {
  const groups = collapseComparison(rows);
  const note = collapsedNote(groups);
  return (
    <section aria-label="Lineup comparison" className="mt-6">
      <table className="hidden w-full text-body lg:table">
        <thead>
          <tr className="border-b border-border text-left text-caption text-muted">
            <th className="py-2 pr-3 font-normal">Lineup</th>
            <th className="pr-3 font-normal">Chance to win</th>
            <th className="pr-3 text-right font-normal">Floor (10%)</th>
            <th className="pr-3 text-right font-normal">Median</th>
            <th className="text-right font-normal">Ceiling (90%)</th>
          </tr>
        </thead>
        <tbody>
          {groups.map(({ labels, row }) => (
            <tr key={labels.join("|")} className="border-b border-border">
              <td className="py-2 pr-3">{labels[0]}</td>
              <td className="pr-3"><WinBar fraction={row.win_prob} /></td>
              <td className="pr-3 text-right tabular-nums">{formatNumber(row.floor, 0)}</td>
              <td className="pr-3 text-right tabular-nums">{formatNumber(row.median, 0)}</td>
              <td className="text-right tabular-nums">{formatNumber(row.ceiling, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="lg:hidden">
        {groups.map(({ labels, row }) => (
          <li key={labels.join("|")} className="border-b border-border py-2">
            <div>{labels[0]}</div>
            <WinBar fraction={row.win_prob} />
            <div className="text-caption text-muted">
              Floor {formatNumber(row.floor, 0)}, median {formatNumber(row.median, 0)}, ceiling{" "}
              {formatNumber(row.ceiling, 0)}
            </div>
          </li>
        ))}
      </ul>
      {note && <p className="mt-2 text-caption text-muted">{note}</p>}
      <p className="mt-2 text-caption text-muted">{COMPARISON_CAPTION}</p>
    </section>
  );
}
