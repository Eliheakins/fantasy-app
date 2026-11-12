import type { League } from "@/api/types";
import type { ApiState } from "@/api/envelope";
import {
  LIVE_NOTE,
  type ScoreboardRow,
  type ScoreboardSide,
  isMine,
  matchupStatus,
  orderedSides,
  sideName,
  sideScore,
  sortMineFirst,
} from "@/lib/scoreboard";
import { PlayoffLabel } from "@/components/PlayoffLabel";
import { cn } from "@/lib/utils";
import { useAllLeagues, useEachLeague } from "@/lib/league";
import { leagueName } from "./weekLogic";

/** The side that won a final, or null while the matchup is open or tied. */
function winnerId(row: ScoreboardRow): number | null {
  if (row.status !== "Final" || row.a.points === row.b.points) return null;
  return (row.a.points > row.b.points ? row.a : row.b).roster_id;
}

function spoken(side: ScoreboardSide, status: ScoreboardRow["status"]): string {
  const s = sideScore(side, status);
  const unit = s.unit === "final" ? "" : s.unit === "proj" ? " projected" : " so far";
  return `${sideName(side)} ${s.value}${unit}${s.win ? `, ${s.win} to win` : ""}`;
}

function TeamLine({ side, row, winner }: { side: ScoreboardSide; row: ScoreboardRow; winner: number | null }) {
  const s = sideScore(side, row.status);
  const lost = winner !== null && winner !== side.roster_id;
  return (
    <div className="flex items-baseline gap-3">
      <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2">
        <span className={cn("max-w-full truncate", side.is_me && "font-semibold")}>{sideName(side)}</span>
        {s.win && (
          <span className="whitespace-nowrap text-caption text-muted">
            {s.projected ? `proj ${s.projected} · ` : ""}
            {s.win} to win
          </span>
        )}
      </span>
      <span className={cn("min-w-16 whitespace-nowrap text-right text-heading tabular-nums", lost ? "text-muted" : "font-semibold")}>
        {s.unit === "proj" && <span className="mr-1 text-caption font-normal text-muted">proj</span>}
        {s.value}
      </span>
    </div>
  );
}

function Matchup({ row, kickoff }: { row: ScoreboardRow; kickoff: Date | null }) {
  const [first, second] = orderedSides(row);
  const status = matchupStatus(row.status, kickoff);
  const winner = winnerId(row);
  return (
    <li
      aria-label={`${row.playoff_label ? `${row.playoff_label}: ` : ""}${spoken(first, row.status)}, ${spoken(second, row.status)}, ${status}`}
      className={cn("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 px-3 py-2", isMine(row) && "mine-row rounded-r-lg")}
    >
      <div className="space-y-1">
        <TeamLine side={first} row={row} winner={winner} />
        <TeamLine side={second} row={row} winner={winner} />
        <PlayoffLabel label={row.playoff_label} />
      </div>
      <span className={cn("w-14 text-right text-caption sm:w-20", row.status === "Live" ? "font-semibold text-ink" : "text-muted")}>
        {status}
      </span>
    </li>
  );
}

function LeagueScores({ league, state, kickoff }: { league: League; state: ApiState<ScoreboardRow[]> | undefined; kickoff: Date | null }) {
  const id = `scores-${league.league_key}`;
  return (
    <section aria-labelledby={id} className="min-w-0">
      <h3 id={id} className="mb-1 px-3 text-body font-semibold text-label">
        {leagueName(league)}
      </h3>
      {state?.kind === "ready" ? (
        state.data.length ? (
          <ul className="divide-y divide-line">
            {sortMineFirst(state.data).map((row) => (
              <Matchup key={`${row.week}-${row.a.roster_id}`} row={row} kickoff={kickoff} />
            ))}
          </ul>
        ) : (
          <p className="px-3 text-body text-muted">No matchups are set for this week yet.</p>
        )
      ) : state?.kind === "error" ? (
        <p role="alert" className="px-3 text-body text-warning">
          The scores did not load: {state.error.message}
        </p>
      ) : (
        <p role="status" className="px-3 text-body text-muted">
          Loading scores…
        </p>
      )}
    </section>
  );
}

/** Every matchup of the week in both leagues, grouped by league, my matchup first on the tint. Always my own teams. */
export function WeekScores({ kickoff }: { kickoff: Date | null }) {
  const leagues = useAllLeagues();
  const list = leagues.kind === "ready" ? leagues.data : [];
  const boards = useEachLeague<ScoreboardRow[]>(
    list.map((l) => l.league_key),
    "scoreboard",
  );
  const rows = boards.flatMap((b) => (b.kind === "ready" ? b.data : []));
  const week = rows[0]?.week;
  if (leagues.kind !== "ready") return null; // the to-do section already reports a league list failure
  return (
    <section aria-labelledby="scores-heading" className="mb-8">
      <h2 id="scores-heading" className="text-section font-semibold">
        {week ? `Scores, week ${week}` : "Scores"}
      </h2>
      <p className="measure mt-1 text-caption text-muted">
        Every matchup in both leagues.{rows.some((r) => r.status === "Live") ? ` ${LIVE_NOTE}` : ""}
      </p>
      <div className="mt-3 grid gap-x-10 gap-y-6 lg:grid-cols-2">
        {list.map((l, i) => (
          <LeagueScores key={l.league_key} league={l} state={boards[i]} kickoff={kickoff} />
        ))}
      </div>
    </section>
  );
}
