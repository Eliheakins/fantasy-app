import { Section } from "@/components/Section";
import { WinBar, formatNumber, formatPercent } from "@/viz";
import { COMPARISON_CAPTION, type ComparisonRow, collapseComparison, collapsedNote } from "./logic";

/** Nothing to compare when every objective plays the same lineup: say so in one line. */
export function Comparison({ rows }: { rows: readonly ComparisonRow[] }) {
  const groups = collapseComparison(rows);
  const [only] = groups;
  if (!only) return null;
  const note = collapsedNote(groups);
  const how = <>{note && <p>{note}</p>}<p>{COMPARISON_CAPTION}</p></>;
  if (groups.length === 1) {
    const r = only.row;
    const [lo, mid, hi] = [r.floor, r.median, r.ceiling].map((v) => formatNumber(v, 0));
    const spread = lo === hi ? `${mid} pts` : `${lo} to ${hi} pts (median ${mid})`;
    return (
      <Section title="Compare lineups" howCalculated={how}>
        <p className="text-body">
          Every way of choosing picks this lineup: {formatPercent(r.win_prob)} to win, team score {spread}.
        </p>
      </Section>
    );
  }
  return (
    <Section title="Compare lineups" howCalculated={how}>
      <table className="hidden w-full text-body lg:table">
        <thead>
          <tr className="border-b border-border text-left text-caption text-muted">
            <th className="py-2 pr-3 font-normal">Lineup</th>
            <th className="pr-3 font-normal">Chance to win</th>
            <th className="pr-3 text-right font-normal">Floor, 10% (pts)</th>
            <th className="pr-3 text-right font-normal">Median (pts)</th>
            <th className="text-right font-normal">Ceiling, 90% (pts)</th>
          </tr>
        </thead>
        <tbody>
          {groups.map(({ labels, row }) => (
            <tr key={labels.join("|")} className="border-b border-border">
              <th scope="row" className="py-2 pr-3 text-left font-normal">{labels[0]}</th>
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
              Floor {formatNumber(row.floor, 0)}, median {formatNumber(row.median, 0)}, ceiling {formatNumber(row.ceiling, 0)} pts
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}
