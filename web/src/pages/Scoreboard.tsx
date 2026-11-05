import type { Status } from "@/api/types";
import { ApiBoundary } from "@/components/ApiBoundary";
import { MatchupCard } from "@/features/scoreboard/MatchupCard";
import {
  EMPTY_WEEK,
  LIVE_NOTE,
  RANGE_LEGEND,
  hasMixedStatus,
  weekStatus,
  type ScoreboardRow,
} from "@/features/scoreboard/logic";
import { useApi } from "@/hooks/useApi";
import { useLeague, useLeagueApi } from "@/lib/league";
import { formatAsOf, latestUpdate } from "@/lib/status";
import { useWeek } from "@/lib/week";

export function ScoreboardView({ rows, week, asOf }: { rows: ScoreboardRow[]; week: number; asOf: string | null }) {
  if (rows.length === 0) return <p className="py-6 text-body text-muted">{EMPTY_WEEK(week)}</p>;
  const live = rows.some((r) => r.status !== "Final");
  const mixed = hasMixedStatus(rows);
  return (
    <>
      <p className="measure text-caption text-muted">
        Week {week}: {weekStatus(rows)}. {live && (asOf ? `Points as of ${asOf}. ` : "")}
        {live && `${LIVE_NOTE} ${RANGE_LEGEND}`}
      </p>
      <ul aria-label={`Week ${week} matchups`} className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {rows.map((row) => (
          <li key={`${row.week}-${row.a.roster_id}`}>
            <MatchupCard row={row} showStatus={mixed} />
          </li>
        ))}
      </ul>
    </>
  );
}

/** Mounted under Season; the week is the global ?week=. */
export default function Scoreboard() {
  const { league } = useLeague();
  const { week } = useWeek();
  const board = useLeagueApi<ScoreboardRow[]>(`scoreboard?week=${week}`);
  const status = useApi<Status>("/api/status");
  const updated = status.kind === "ready" ? latestUpdate(status.data) : null;
  return (
    <div key={league}>
      <ApiBoundary state={board}>
        {(rows) => <ScoreboardView rows={rows} week={week} asOf={updated ? formatAsOf(updated) : null} />}
      </ApiBoundary>
    </div>
  );
}
