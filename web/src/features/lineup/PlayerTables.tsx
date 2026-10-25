import { RangeBar, formatNumber } from "@/viz";
import { type LineupRow, injuryLabel, rangeText, tableDomain } from "./logic";

const BADGE = "rounded border border-border px-1.5 text-caption whitespace-nowrap";

function Badges({ row, known }: { row: LineupRow; known: boolean }) {
  const injury = injuryLabel(row);
  return (
    <span className="inline-flex flex-wrap gap-1">
      {row.change && known && <span className={`${BADGE} font-medium`}>{row.change}</span>}
      {row.locked && <span className={BADGE}>Locked</span>}
      {injury && <span className={BADGE}>{injury}</span>}
    </span>
  );
}

function Bar({ row, domain }: { row: LineupRow; domain: ReturnType<typeof tableDomain> }) {
  if (!domain) return <span>{rangeText(row)}</span>;
  return <RangeBar domain={domain} p10={row.p10} p50={row.projection} p90={row.p90} />;
}

const rowClass = (row: LineupRow) => (row.locked ? "text-muted" : "");

/** Table at md and up, stacked cards on a phone. One shared range axis per table. */
export function PlayerTable({ title, rows, known }: { title: string; rows: readonly LineupRow[]; known: boolean }) {
  const domain = tableDomain(rows);
  return (
    <section aria-label={title} className="mt-6">
      <h2 className="text-heading font-semibold">{title}</h2>
      <table className="mt-2 hidden w-full text-body md:table">
        <thead>
          <tr className="border-b border-border text-left text-caption text-muted">
            <th className="py-2 pr-3 font-normal">Slot</th>
            <th className="pr-3 font-normal">Player</th>
            <th className="pr-3 font-normal">Pos</th>
            <th className="pr-3 text-right font-normal">Proj</th>
            <th className="pr-3 font-normal">10 to 90%</th>
            <th className="pr-3 text-right font-normal">Pts so far</th>
            <th className="pr-3 font-normal">Game</th>
            <th className="font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.gsis_id} className={`border-b border-border ${rowClass(r)}`}>
              <td className="py-2 pr-3">{r.slot}</td>
              <td className="pr-3">{r.full_name}</td>
              <td className="pr-3">{r.position}</td>
              <td className="pr-3 text-right tabular-nums">{formatNumber(r.projection)}</td>
              <td className="pr-3">
                <Bar row={r} domain={domain} />
                <span className="ml-2 tabular-nums text-caption text-muted">{rangeText(r)}</span>
              </td>
              <td className="pr-3 text-right tabular-nums">{formatNumber(r.actual)}</td>
              <td className="pr-3">{r.game}</td>
              <td><Badges row={r} known={known} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="mt-2 md:hidden">
        {rows.map((r) => (
          <li key={r.gsis_id} className={`min-h-[44px] border-b border-border py-2 ${rowClass(r)}`}>
            <div className="flex items-baseline justify-between gap-2">
              <span>
                <span className="text-muted">{r.slot}</span> {r.full_name} <span className="text-muted">{r.position}</span>
              </span>
              <span className="tabular-nums">{formatNumber(r.projection)}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <Bar row={r} domain={domain} />
              <span className="tabular-nums text-caption text-muted">{rangeText(r)}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-caption text-muted">
              <span>{r.game}</span>
              <span>Pts so far {formatNumber(r.actual)}</span>
              <Badges row={r} known={known} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
