import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { PlayerLink } from "@/components/PlayerLink";
import { Section } from "@/components/Section";
import { RangeBar, formatNumber } from "@/viz";
import { type LineupRow, hasRange, injuryLabel, pointsSoFar, rangeText, slotHidesPosition, slotLabel, tableDomain } from "./logic";

const NO_VALUE = "–";

type Ctx = { known: boolean; domain: ReturnType<typeof tableDomain>; final: boolean; started: boolean };
type Column = { head: string; width: string; right?: boolean; cell: (r: LineupRow, c: Ctx) => ReactNode };

/** Injury note as amber text under the name, never a boxed chip. */
function Injury({ row }: { row: LineupRow }) {
  const injury = injuryLabel(row);
  return injury ? <span className="block text-caption text-warning">{injury}</span> : null;
}

/** One status per row: the change against Sleeper, else a lock with its label. */
function Status({ row, known }: { row: LineupRow; known: boolean }) {
  if (row.change && known) return <span className="font-medium text-ink">{row.change}</span>;
  if (!row.locked) return null;
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap text-muted">
      <Lock aria-hidden size={13} />
      Locked
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

const SLOT: Column = { head: "Slot", width: "10%", cell: (r) => slotLabel(r.slot) };
const PLAYER: Column = {
  head: "Player",
  width: "24%",
  cell: (r) => (
    <>
      <PlayerLink gsisId={r.gsis_id} name={r.full_name} position={r.position} />
      <Injury row={r} />
    </>
  ),
};
const POS: Column = { head: "Pos", width: "7%", cell: (r) => r.position };
const GAME: Column = { head: "Game", width: "14%", cell: (r) => r.game };

/** Final week: what each player scored. Otherwise projection, then range, points so far and status only when some row has one. */
function columnsFor(rows: readonly LineupRow[], final: boolean): Column[] {
  if (final) {
    return [
      { ...SLOT, width: "14%" },
      { ...PLAYER, width: "44%" },
      { ...POS, width: "10%" },
      { head: "Points", width: "12%", right: true, cell: (r) => formatNumber(r.actual) },
      { ...GAME, width: "20%" },
    ];
  }
  const started = hasStarted(rows);
  const status = rows.some((r) => r.locked || r.change);
  return [
    SLOT,
    PLAYER,
    POS,
    { head: "Proj (pts)", width: "9%", right: true, cell: (r) => formatNumber(r.projection) },
    ...(rows.some(hasRange)
      ? [{ head: "Range, 10 to 90% (pts)", width: "24%", cell: (r: LineupRow, c: Ctx) => <Bar row={r} domain={c.domain} /> }]
      : []),
    ...(started ? [{ head: "Pts so far", width: "9%", right: true, cell: (r: LineupRow) => pointsSoFar(r) }] : []),
    GAME,
    ...(status ? [{ head: "Status", width: "11%", cell: (r: LineupRow, c: Ctx) => <Status row={r} known={c.known} /> }] : []),
  ];
}

function hasStarted(rows: readonly LineupRow[]): boolean {
  return rows.some((r) => r.locked || r.actual !== 0);
}

/** A locked row reads as settled while other games are left; in a finished week nothing is greyed. */
const rowClass = (row: LineupRow, final: boolean) => (row.locked && !final ? "text-muted" : "");

function Wide({ rows, ctx, columns }: { rows: readonly LineupRow[]; ctx: Ctx; columns: Column[] }) {
  return (
    <table className="hidden w-full table-fixed text-body lg:table">
      <colgroup>
        {columns.map((c) => (
          <col key={c.head} style={{ width: c.width }} />
        ))}
      </colgroup>
      <thead>
        <tr className="border-b-[1.5px] border-forest text-left text-caption text-muted">
          {columns.map((c) => (
            <th key={c.head} scope="col" className={`py-2 pr-3 font-normal last:pr-0 ${c.right ? "text-right" : ""}`}>
              {c.head}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.gsis_id} className={`border-b border-line align-top ${rowClass(r, ctx.final)}`}>
            {columns.map((c) =>
              c.head === PLAYER.head ? (
                <th key={c.head} scope="row" className="py-2 pr-3 text-left font-normal text-ink">
                  {c.cell(r, ctx)}
                </th>
              ) : (
                <td key={c.head} className={`py-2 pr-3 last:pr-0 ${c.right ? "text-right tabular-nums" : ""}`}>
                  {c.cell(r, ctx)}
                </td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Cards({ rows, ctx }: { rows: readonly LineupRow[]; ctx: Ctx }) {
  return (
    <ul className="lg:hidden">
      {rows.map((r) => (
        <li key={r.gsis_id} className={`min-h-[44px] border-b border-line py-2 ${rowClass(r, ctx.final)}`}>
          <div className="flex items-baseline justify-between gap-2">
            <span>
              <span className="text-muted">{slotLabel(r.slot)}</span>{" "}
              <span className="text-ink">
                <PlayerLink gsisId={r.gsis_id} name={r.full_name} position={r.position} />
              </span>
              {slotHidesPosition(r.slot) && <span className="text-muted"> {r.position}</span>}
            </span>
            <span className="whitespace-nowrap tabular-nums text-ink">
              {formatNumber(ctx.final ? r.actual : r.projection)}{" "}
              <span className="text-caption text-muted">{ctx.final ? "pts" : "proj"}</span>
            </span>
          </div>
          <Injury row={r} />
          {!ctx.final && hasRange(r) && (
            <div className="mt-1">
              <Bar row={r} domain={ctx.domain} />
            </div>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 text-caption text-muted">
            <span>{r.game}</span>
            {!ctx.final && ctx.started && <span>Pts so far {pointsSoFar(r)}</span>}
            {!ctx.final && <Status row={r} known={ctx.known} />}
          </div>
        </li>
      ))}
    </ul>
  );
}

type Props = { title: string; rows: readonly LineupRow[]; known: boolean; final?: boolean; caption?: ReactNode; howCalculated?: ReactNode };

/** Table at lg and up, stacked cards below it. One shared range axis per table; no range column when no row has one. */
export function PlayerTable({ title, rows, known, final = false, caption, howCalculated }: Props) {
  const ctx = { known, final, started: hasStarted(rows), domain: tableDomain(rows) };
  return (
    <Section title={title} caption={caption} howCalculated={howCalculated}>
      <Wide rows={rows} ctx={ctx} columns={columnsFor(rows, final)} />
      <Cards rows={rows} ctx={ctx} />
    </Section>
  );
}
