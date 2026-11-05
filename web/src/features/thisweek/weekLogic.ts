import type { components } from "@/api/schema";

export type WeekCalendar = components["schemas"]["WeekCalendarData"];
type Kickoff = WeekCalendar["kickoffs"][number];
type TimedKickoff = { team: string; kickoff: string };
const timed = (ks: readonly Kickoff[]): TimedKickoff[] =>
  ks.flatMap((k) => (k.kickoff === null ? [] : [{ team: k.team, kickoff: k.kickoff }]));

/** The NFL week is shown in New York time, the zone of the schedule. */
const ZONE = "America/New_York";
const DAY_FORMAT = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const TIME_FORMAT = new Intl.DateTimeFormat("en-US", { timeZone: ZONE, hour: "numeric", minute: "2-digit" });
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const TUESDAY = 2;
const DAYS_IN_WEEK = 7;
const FRIDAY_POSITION = 3; // Tue Wed Thu Fri
const MONDAY_ZERO_TO_STRIP = DAYS_IN_WEEK - 1; // Sleeper counts Monday as 0; the strip starts on Tuesday

/** "2026-11-04": the New York calendar day of an instant. */
export const etDay = (at: Date): string => DAY_FORMAT.format(at);

const dayAsDate = (day: string): Date => new Date(`${day}T12:00:00Z`);

export function addDays(day: string, n: number): string {
  const d = dayAsDate(day);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export const weekdayLabel = (day: string): string => WEEKDAYS[dayAsDate(day).getUTCDay()] ?? "";

/** "Wed 11": the weekday with the date, so a deadline next week is not mistaken for this week's. */
export const dayLabel = (day: string): string => `${weekdayLabel(day)} ${Number(day.slice(8))}`;

/** Tuesday to Monday around `now`: the NFL week turns over on Tuesday. */
export function weekDays(now: Date): string[] {
  const today = etDay(now);
  const sinceTuesday = (dayAsDate(today).getUTCDay() - TUESDAY + DAYS_IN_WEEK) % DAYS_IN_WEEK;
  const start = addDays(today, -sinceTuesday);
  return Array.from({ length: DAYS_IN_WEEK }, (_, i) => addDays(start, i));
}

/** Day the league's waivers clear (this week's, or next week's once it has passed); null when not known. */
export function waiverDeadlineDay(dayOfWeek: number | null, now: Date): string | null {
  if (dayOfWeek === null) return null;
  const day = weekDays(now)[(dayOfWeek + MONDAY_ZERO_TO_STRIP) % DAYS_IN_WEEK];
  if (day === undefined) return null;
  return day < etDay(now) ? addDays(day, DAYS_IN_WEEK) : day;
}

/** Day of the next kickoff still to come: lineups can still change until then. */
export function lineupDeadlineDay(kickoffs: readonly Kickoff[], now: Date): string | null {
  const ahead = timed(kickoffs).map((k) => new Date(k.kickoff)).filter((t) => t.getTime() > now.getTime());
  if (ahead.length === 0) return null;
  return etDay(new Date(Math.min(...ahead.map((t) => t.getTime()))));
}

export type StripEvent = { kind: "waivers" | "injury" | "kickoff"; text: string };
export type StripDay = { day: string; label: string; dayOfMonth: number; isToday: boolean; isPast: boolean; events: StripEvent[] };

function kickoffEvent(group: readonly TimedKickoff[]): StripEvent {
  const games = Math.max(1, Math.floor(group.length / 2));
  const first = new Date(Math.min(...group.map((k) => Date.parse(k.kickoff))));
  const time = TIME_FORMAT.format(first).replace(/\s/g, " ");
  return { kind: "kickoff", text: `${games} game${games === 1 ? "" : "s"}, first ${time}` };
}

/** The seven days with "now" marked and what is due on each: waivers, the Friday injury report, kickoffs. */
export function buildStrip(now: Date, calendar: WeekCalendar): StripDay[] {
  const days = weekDays(now);
  const today = etDay(now);
  const onDay = new Map<string, StripEvent[]>(days.map((d) => [d, []]));
  const add = (day: string | undefined, event: StripEvent) => day !== undefined && onDay.get(day)?.push(event);
  const byDay = new Map<string, TimedKickoff[]>();
  for (const k of timed(calendar.kickoffs)) {
    const day = etDay(new Date(k.kickoff));
    byDay.set(day, [...(byDay.get(day) ?? []), k]);
  }
  const clearing = new Map<string, string[]>();
  for (const w of calendar.waivers) {
    if (w.day_of_week === null || w.daily) continue;
    const day = days[(w.day_of_week + MONDAY_ZERO_TO_STRIP) % DAYS_IN_WEEK];
    if (day !== undefined) clearing.set(day, [...(clearing.get(day) ?? []), w.name?.trim() || w.league_key]);
  }
  for (const [day, names] of clearing) add(day, { kind: "waivers", text: `Waivers clear: ${names.join(", ")}` });
  add(days[FRIDAY_POSITION], { kind: "injury", text: "Injury report" });
  for (const [day, group] of byDay) add(day, kickoffEvent(group));
  return days.map((day) => ({
    day, label: weekdayLabel(day), dayOfMonth: Number(day.slice(8)), isToday: day === today, isPast: day < today,
    events: onDay.get(day) ?? [],
  }));
}

/** Leagues whose waiver clear day cannot be placed, with why. */
export function unplacedWaivers(calendar: WeekCalendar): string[] {
  return calendar.waivers
    .filter((w) => w.daily || w.day_of_week === null)
    .map((w) => `${w.name?.trim() || w.league_key}: ${w.daily ? "daily waivers, no single clear day" : "no waiver day in the data"}`);
}

/** What the strip cannot show: kickoffs on days outside it (data behind the calendar) and teams with no kickoff time. */
export function stripNotes(now: Date, calendar: WeekCalendar): string[] {
  const days = new Set(weekDays(now));
  const known = timed(calendar.kickoffs);
  const outside = known.filter((k) => !days.has(etDay(new Date(k.kickoff)))).length;
  const week = calendar.week === null ? "the current week" : `week ${calendar.week}`;
  const notes: string[] = [];
  if (known.length > 0 && outside === known.length) {
    notes.push(`All kickoffs for ${week} are outside this Tuesday to Monday strip, so none are shown. The data may be behind: run make refresh.`);
  } else if (outside > 0) {
    notes.push(`${outside} kickoffs for ${week} fall outside this strip and are not shown.`);
  }
  const unknown = calendar.kickoffs.length - known.length;
  if (unknown > 0) notes.push(`${unknown} teams have no kickoff time on the schedule.`);
  return notes;
}
