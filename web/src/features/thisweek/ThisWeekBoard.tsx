import { GameDay, useLiveStatus } from "./GameDay";
import { SinceLastLooked } from "./SinceLastLooked";
import { TodoList } from "./TodoList";
import { useTodos } from "./useTodos";
import { WeekScores } from "./WeekScores";
import { firstKickoff } from "@/lib/scoreboard";
import { WeekStrip } from "./WeekStrip";

/** The week strip, the to-do list for both leagues (the page's tinted panel, unless game day takes it), every matchup's score and the visit changes. */
export function ThisWeekBoard() {
  const { pending, todos, failed, calendar, calendarFailed, leaguesError, now } = useTodos();
  const { live, intervalMs } = useLiveStatus();
  return (
    <>
      {live && <GameDay intervalMs={intervalMs} />}
      {calendar && <WeekStrip calendar={calendar} now={now} />}
      {calendarFailed && <p className="mb-4 text-caption text-muted">The week calendar did not load, so deadlines are not shown.</p>}
      <section aria-labelledby="todo-heading" className={live ? "mb-6" : "mb-6 key-panel"}>
        <h2 id="todo-heading" className="mb-3 text-section font-semibold">To do, both leagues</h2>
        {leaguesError !== null ? (
          <p role="alert" className="text-body text-warning">The leagues did not load, so there are no to-dos to show: {leaguesError}</p>
        ) : pending ? (
          <p role="status" className="text-muted">Loading your to-dos…</p>
        ) : (
          <TodoList todos={todos} />
        )}
        {failed.length > 0 && <p role="alert" className="mt-3 text-caption text-warning">Some to-dos did not load for: {failed.join(", ")}.</p>}
        <p className="measure mt-3 text-caption text-muted">
          Ordered by what expires first, then by effect: playoff-odds change first, then fantasy points, then items with no number. The two units are not converted into each other.
        </p>
      </section>
      <WeekScores kickoff={calendar ? firstKickoff(calendar.kickoffs) : null} />
      <SinceLastLooked />
    </>
  );
}
