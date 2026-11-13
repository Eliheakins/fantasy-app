import { Link } from "react-router-dom";
import type { components } from "@/api/schema";
import { formatNumber } from "@/viz";

export type LineupGrid = components["schemas"]["LineupGrid"];
type GridRow = components["schemas"]["GridRow"];
type Flag = NonNullable<GridRow["flag"]>;

const FLAG_TEXT: Record<Flag, { label: string; reason: string }> = {
  bye: { label: "Bye", reason: "the best player for this slot is on a bye" },
  out: { label: "Out", reason: "the starter is out or on IR" },
  weak: { label: "Weak", reason: "a free agent would score more" },
};
const POSITION_SLOTS = new Set(["QB", "RB", "WR", "TE", "K", "DEF"]);
const CELL = "min-w-[8rem] border-b border-line px-3 py-2 align-top";

/** Moves filtered to the slot's position; a flex slot has no single position, so it opens all adds. */
const movesHref = (league: string, slot: string) =>
  `/moves?league=${encodeURIComponent(league)}${POSITION_SLOTS.has(slot) ? `&pos=${slot}` : ""}`;

function Cell({ row, league }: { row: GridRow; league: string }) {
  const flag = row.flag ? FLAG_TEXT[row.flag] : null;
  return (
    <>
      <div className="font-medium">{row.full_name ?? "No player"}</div>
      <div className="tabular-nums text-muted">{formatNumber(row.points)}</div>
      {flag && (
        <div className="mt-1 text-caption">
          <span className="font-semibold">{flag.label}</span>
          <span className="sr-only">{`: ${flag.reason}.`}</span>{" "}
          <Link to={movesHref(league, row.slot)} className="inline-flex min-h-[44px] items-center underline underline-offset-2 lg:min-h-0">
            Find a {row.slot} <span className="sr-only">for week {row.week}</span>
          </Link>
        </div>
      )}
    </>
  );
}

/** My auto-lineup for each remaining week, one column per week and one row per slot. */
export function WeeksAheadGrid({ grid, league }: { grid: LineupGrid; league: string }) {
  if (grid.weeks.length === 0) return <p className="py-6 text-muted">Season over</p>;
  const current = grid.weeks[0];
  const slots = grid.rows.filter((r) => r.week === current).map((r) => r.slot);
  const cellOf = (week: number, index: number) => grid.rows.filter((r) => r.week === week)[index];
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Weeks ahead lineup">
      <table className="w-full border-collapse text-left text-body">
        <caption className="mb-2 text-left text-caption text-muted">
          Weeks ahead: your best lineup for each remaining week, through the last playoff week. Points are expected points.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="sticky left-0 z-10 border-b border-line bg-page px-3 py-2">
              Slot
            </th>
            {grid.weeks.map((w) => (
              <th key={w} scope="col" className="border-b border-line px-3 py-2">
                Week {w}
                {w === current && (
                  <>
                    {" "}
                    <span className="sr-only">this week</span>
                  </>
                )}
                {grid.playoff_weeks.includes(w) && <span className="block text-caption font-normal text-muted">playoffs</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slots.map((slot, i) => (
            <tr key={`${slot}-${i}`}>
              <th scope="row" className="sticky left-0 z-10 border-b border-line bg-page px-3 py-2 font-medium">
                {slot}
              </th>
              {grid.weeks.map((w) => {
                const row = cellOf(w, i);
                return (
                  <td key={w} className={CELL}>
                    {row ? <Cell row={row} league={league} /> : "–"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
