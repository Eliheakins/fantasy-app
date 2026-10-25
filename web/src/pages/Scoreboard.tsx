import { PageHeader } from "@/components/PageHeader";
import { useState } from "react";
import type { Status } from "@/api/types";
import { ApiBoundary } from "@/components/ApiBoundary";
import { MatchupCard } from "@/features/scoreboard/MatchupCard";
import {
  EMPTY_WEEK,
  FIRST_WEEK,
  LAST_WEEK,
  LIVE_NOTE,
  type ScoreboardRow,
  clampWeek,
} from "@/features/scoreboard/logic";
import { useApi } from "@/hooks/useApi";
import { useLeague, useLeagueApi } from "@/lib/league";
import { formatAsOf, latestUpdate } from "@/lib/status";

const WEEKS = Array.from({ length: LAST_WEEK }, (_, i) => i + FIRST_WEEK);
const STEP_CLASS = "min-h-[44px] min-w-[44px] rounded-md border border-border px-3 text-body disabled:opacity-40";

export function ScoreboardView({ rows, week, asOf }: { rows: ScoreboardRow[]; week: number; asOf: string | null }) {
  if (rows.length === 0) return <p className="py-6 text-body text-muted">{EMPTY_WEEK(week)}</p>;
  const live = rows.some((r) => r.status !== "Final");
  return (
    <>
      <ul aria-label={`Week ${week} matchups`} className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {rows.map((row) => (
          <li key={`${row.week}-${row.a.roster_id}`}>
            <MatchupCard row={row} />
          </li>
        ))}
      </ul>
      {live && (
        <p className="mt-4 text-caption text-muted">
          {asOf ? `Points as of ${asOf}. ` : ""}
          {LIVE_NOTE}
        </p>
      )}
    </>
  );
}

export default function Scoreboard() {
  const { league, leagues } = useLeague();
  // Keyed by league so a week picked in one league does not carry to the other.
  const [picked, setPicked] = useState<{ league: string | null; week: number } | null>(null);
  const current = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league)?.current_week : null;
  const week = clampWeek((picked?.league === league ? picked.week : null) ?? current ?? FIRST_WEEK);
  const board = useLeagueApi<ScoreboardRow[]>(`scoreboard?week=${week}`);
  const status = useApi<Status>("/api/status");
  const updated = status.kind === "ready" ? latestUpdate(status.data) : null;
  const go = (next: number) => setPicked({ league, week: clampWeek(next) });
  return (
    <div key={league}>
      <PageHeader
        title="Scoreboard"
        actions={
        <div role="group" aria-label="Week" className="flex items-center gap-2">
          <button type="button" className={STEP_CLASS} disabled={week <= FIRST_WEEK} onClick={() => go(week - 1)} aria-label="Previous week">
            ‹
          </button>
          <label className="flex items-center gap-2 text-body">
            Week
            <select
              value={week}
              onChange={(e) => go(Number(e.target.value))}
              className="min-h-[44px] rounded-md border border-border bg-transparent px-2"
            >
              {WEEKS.map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </label>
          <button type="button" className={STEP_CLASS} disabled={week >= LAST_WEEK} onClick={() => go(week + 1)} aria-label="Next week">
            ›
          </button>
        </div>
        }
      />
      <ApiBoundary state={board}>
        {(rows) => <ScoreboardView rows={rows} week={week} asOf={updated ? formatAsOf(updated) : null} />}
      </ApiBoundary>
    </div>
  );
}
