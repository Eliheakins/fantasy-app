import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { formatNumber } from "@/viz";
import { HBar } from "./PowerRankings";
import { GRADE_POSITIONS, type GradePosition, type GradeTeam, barFraction, gradeGrid, ordinal } from "./logic";
import type { TeamGradeRow } from "./types";

const HEADINGS: Record<GradePosition, string> = { overall: "Overall", QB: "QB", RB: "RB", WR: "WR", TE: "TE" };

const detail = (c: TeamGradeRow) =>
  `starters ${formatNumber(c.vor_per_week)} pts/wk, depth ${formatNumber(c.depth_per_week)} pts/wk`;

/** Grade and rank in text, the starter bar for length, the starters/depth split behind a tap. */
function Cell({ cell, max }: { cell: TeamGradeRow | undefined; max: number }) {
  if (!cell) return <span className="text-muted">–</span>;
  return (
    <span className="block min-w-[7rem]" title={detail(cell)}>
      <details>
        <summary className="min-h-[44px] cursor-pointer py-1 md:min-h-0">
          <span className="font-semibold">{cell.grade}</span> <span className="tabular-nums">{ordinal(cell.rank)}</span>
        </summary>
        <span className="block text-caption text-muted">{detail(cell)}</span>
      </details>
      <HBar fraction={barFraction(cell.vor_per_week, max)} label={detail(cell)} />
    </span>
  );
}

export function PositionalStrength({ rows }: { rows: readonly TeamGradeRow[] }) {
  const teams = gradeGrid(rows);
  const max = (p: GradePosition) => Math.max(0, ...teams.map((t) => t.cells[p]?.vor_per_week ?? 0));
  const columns: Column<GradeTeam>[] = [
    { label: "Team", role: "primary", render: (t) => (t.is_me ? `${t.team_name} (you)` : t.team_name) },
    ...GRADE_POSITIONS.map((p) => ({ label: HEADINGS[p], render: (t: GradeTeam) => <Cell cell={t.cells[p]} max={max(p)} /> })),
  ];
  return (
    <ResponsiveTable caption="Positional strength by team" columns={columns} rows={teams} rowKey={(t) => String(t.roster_id)} isStrong={(t) => t.is_me} />
  );
}
