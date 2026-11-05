import { type WeekCalendar, buildStrip, stripNotes, unplacedWaivers } from "./weekLogic";

/** Tuesday to Monday of the NFL week: "Now" on today, waiver clears, the injury report and kickoffs. */
export function WeekStrip({ calendar, now }: { calendar: WeekCalendar; now: Date }) {
  const days = buildStrip(now, calendar);
  const unplaced = unplacedWaivers(calendar);
  const notes = stripNotes(now, calendar);
  return (
    <section aria-labelledby="week-strip-heading" className="mb-6">
      <h2 id="week-strip-heading" className="mb-2 text-section font-semibold">The week</h2>
      {/* phones list only today and the days with something on, so the to-dos stay near the top */}
      <ol className="grid grid-cols-1 gap-2 sm:grid-cols-7">
        {days.map((d) => (
          <li
            key={d.day}
            aria-current={d.isToday ? "date" : undefined}
            className={`min-w-0 rounded-lg border px-2 py-2 text-caption ${d.isToday ? "border-2 border-forest" : "border-line"} ${d.isPast ? "text-muted" : ""} ${d.events.length === 0 && !d.isToday ? "hidden sm:block" : ""}`}
          >
            <div className="font-semibold">
              {d.label} {d.dayOfMonth}
              {d.isPast && <span className="sr-only"> (past)</span>}
              {d.isToday && <span className="ml-1 rounded bg-forest px-1 text-white">Now</span>}
            </div>
            {d.events.map((e) => <div key={e.text}>{e.text}</div>)}
          </li>
        ))}
      </ol>
      {notes.map((n) => <p key={n} role="status" className="measure mt-2 text-caption text-warning">{n}</p>)}
      <p className="measure mt-2 text-caption text-muted">
        Times are New York. Sleeper gives the waiver day, not the hour; the Friday injury report is the NFL's usual schedule.
        {unplaced.length > 0 && ` Not available: ${unplaced.join("; ")}.`}
      </p>
    </section>
  );
}
