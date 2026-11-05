import { useMemo } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { OddsHistoryChart } from "@/features/outlook/OddsHistoryChart";
import { HISTORY_WAIT_MESSAGE, canShowHistory, formatRunDate } from "@/features/outlook/logic";
import type { OddsHistoryRow, SeasonOddsRow } from "@/features/outlook/types";
import { useLeagueApi } from "@/lib/league";
import { formatPercent } from "@/viz";
import { eventMarks, myOddsByRun } from "./logic";
import type { SeasonEventRow } from "./types";

const EVENTS_ID = "season-marked-events";
const KIND_LABEL = { trade: "Trade", injury: "Injury", big_week: "Big week" } as const;
const MISSING =
  "Marked: your trades, injuries to your starters (Sleeper's Out, IR or Doubtful, from the daily snapshots) and weeks far above your average. Not marked: waiver moves, and anything before the first saved run.";

function placement(e: SeasonEventRow, mine: ReadonlyMap<string, number>): string {
  if (e.run_at === null) return "before the first saved run, so not drawn";
  return `your odds ${formatPercent(mine.get(e.run_at))} at the ${formatRunDate(e.run_at)} run`;
}

function EventList({ events, mine }: { events: readonly SeasonEventRow[]; mine: ReadonlyMap<string, number> }) {
  return (
    <div className="mt-2">
      <h3 id={EVENTS_ID} className="text-body font-semibold">Marked events</h3>
      {events.length === 0 ? (
        <p className="text-caption text-muted">Nothing to mark yet.</p>
      ) : (
        <ul aria-labelledby={EVENTS_ID} className="text-caption">
          {events.map((e) => (
            <li key={`${e.kind}-${e.when}-${e.label}`} className="py-0.5">
              {!e.label.startsWith(KIND_LABEL[e.kind]) && <span className="sr-only">{KIND_LABEL[e.kind]}: </span>}
              {e.label} <span className="text-muted">({placement(e, mine)})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Chart({ odds, history, events }: { odds: SeasonOddsRow[]; history: OddsHistoryRow[]; events: ReturnType<typeof useLeagueApi<SeasonEventRow[]>> }) {
  const list = useMemo(() => (events.kind === "ready" ? events.data : []), [events]);
  const marks = useMemo(() => new Set(eventMarks(list).byRun.keys()), [list]);
  const mine = useMemo(() => myOddsByRun(history, odds.find((o) => o.is_me)?.roster_id), [history, odds]);
  if (!canShowHistory(odds, history)) return <p className="measure text-caption text-muted">{HISTORY_WAIT_MESSAGE}</p>;
  return (
    <>
      <OddsHistoryChart odds={odds} history={history} marks={marks} describedBy={EVENTS_ID} />
      {events.kind === "error" ? (
        <p role="alert" id={EVENTS_ID} className="mt-2 text-caption text-warning">Marks unavailable: {events.error.message}</p>
      ) : events.kind === "ready" ? (
        <EventList events={list} mine={mine} />
      ) : (
        <p id={EVENTS_ID} className="mt-2 text-caption text-muted">Loading marks…</p>
      )}
    </>
  );
}

/** The odds chart with my trades, starter injuries and big weeks marked on my line. */
export function SeasonOdds() {
  const odds = useLeagueApi<SeasonOddsRow[]>("season-odds");
  const history = useLeagueApi<OddsHistoryRow[]>("odds-history");
  const events = useLeagueApi<SeasonEventRow[]>("season-events");
  return (
    <Section title="Playoff odds over the season" caption="Chance to make the playoffs after each saved run; your line is bold." howCalculated={MISSING}>
      <ApiBoundary state={odds}>
        {(o) => <ApiBoundary state={history}>{(h) => <Chart odds={o} history={h} events={events} />}</ApiBoundary>}
      </ApiBoundary>
    </Section>
  );
}
