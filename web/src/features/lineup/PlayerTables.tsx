import type { ReactNode } from "react";
import { Section } from "@/components/Section";
import { RangeBar, formatNumber } from "@/viz";
import {
  type LineupRow, hasRange, injuryLabel, pointsSoFar, rangeText, slotHidesPosition, slotLabel, tableDomain,
} from "./logic";

const BADGE = "rounded border border-border px-1.5 text-caption";
const NO_VALUE = "–";
/** Shared by Start and Bench so the two tables line up. */
const COLUMN_WIDTHS = ["6%", "17%", "6%", "8%", "20%", "8%", "13%", "22%"];

function Badges({ row, known }: { row: LineupRow; known: boolean }) {
  const injury = injuryLabel(row);
  return (
    <span className="inline-flex flex-wrap gap-1">
      {row.change && known && <span className={`${BADGE} font-medium`}>{row.change}</span>}
      {row.locked && <span className={`${BADGE} whitespace-nowrap`}>Locked</span>}
      {injury && <span className={BADGE}>{injury}</span>}
    </span>
  );
}

function Bar({ row, domain }: { row: LineupRow; domain: ReturnType<typeof tableDomain> }) {
  if (!hasRange(row)) return <span className="text-caption text-muted">{NO_VALUE}</span>;
  return (
    <span className="inline-flex items-center gap-2">
      {domain && <RangeBar domain={domain} p10={row.p10} p50={row.projection} p90={row.p90} />}
      <span className="whitespace-nowrap text-caption tabular-nums text-muted">{rangeText(row)}</span>
    </span>
  );
}

const rowClass = (row: LineupRow) => (row.locked ? "text-muted" : "");

function Head({ children, right }: { children: ReactNode; right?: boolean }) {
  return <th scope="col" className={`py-2 pr-3 font-normal ${right ? "text-right" : ""}`}>{children}</th>;
}

function Wide({ rows, known, domain }: { rows: readonly LineupRow[]; known: boolean; domain: ReturnType<typeof tableDomain> }) {
  return (
    <table className="hidden w-full table-fixed text-body lg:table">
      <colgroup>{COLUMN_WIDTHS.map((w, i) => <col key={i} style={{ width: w }} />)}</colgroup>
      <thead>
        <tr className="border-b border-border text-left text-caption text-muted">
          <Head>Slot</Head>
          <Head>Player</Head>
          <Head>Pos</Head>
          <Head right>Proj (pts)</Head>
          <Head>Range, 10 to 90% (pts)</Head>
          <Head right>Pts so far</Head>
          <Head>Game</Head>
          <th scope="col" className="py-2 font-normal">Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.gsis_id} className={`border-b border-border align-top ${rowClass(r)}`}>
            <td className="py-2 pr-3">{slotLabel(r.slot)}</td>
            <th scope="row" className="py-2 pr-3 text-left font-normal text-text">{r.full_name}</th>
            <td className="py-2 pr-3">{r.position}</td>
            <td className="py-2 pr-3 text-right tabular-nums">{formatNumber(r.projection)}</td>
            <td className="py-2 pr-3"><Bar row={r} domain={domain} /></td>
            <td className="py-2 pr-3 text-right tabular-nums">{pointsSoFar(r)}</td>
            <td className="py-2 pr-3">{r.game}</td>
            <td className="py-2"><Badges row={r} known={known} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Cards({ rows, known, domain }: { rows: readonly LineupRow[]; known: boolean; domain: ReturnType<typeof tableDomain> }) {
  return (
    <ul className="lg:hidden">
      {rows.map((r) => (
        <li key={r.gsis_id} className={`min-h-[44px] border-b border-border py-2 ${rowClass(r)}`}>
          <div className="flex items-baseline justify-between gap-2">
            <span>
              <span className="text-muted">{slotLabel(r.slot)}</span> <span className="text-text">{r.full_name}</span>
              {slotHidesPosition(r.slot) && <span className="text-muted"> {r.position}</span>}
            </span>
            <span className="whitespace-nowrap tabular-nums text-text">{formatNumber(r.projection)} <span className="text-caption text-muted">proj</span></span>
          </div>
          <div className="mt-1"><Bar row={r} domain={domain} /></div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-caption text-muted">
            <span>{r.game}</span>
            <span>Pts so far {pointsSoFar(r)}</span>
            <Badges row={r} known={known} />
          </div>
        </li>
      ))}
    </ul>
  );
}

type Props = { title: string; rows: readonly LineupRow[]; known: boolean; caption?: ReactNode; howCalculated?: ReactNode };

/** Table at lg and up, stacked cards below it. One shared range axis per table. */
export function PlayerTable({ title, rows, known, caption, howCalculated }: Props) {
  const domain = tableDomain(rows);
  return (
    <Section title={title} caption={caption} howCalculated={howCalculated}>
      <Wide rows={rows} known={known} domain={domain} />
      <Cards rows={rows} known={known} domain={domain} />
    </Section>
  );
}
