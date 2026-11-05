import { Section } from "@/components/Section";
import { OddsHistoryChart } from "@/features/outlook/OddsHistoryChart";
import { HISTORY_WAIT_MESSAGE, canShowHistory, formatRunDate } from "@/features/outlook/logic";
import type { OddsHistoryRow, SeasonOddsRow } from "@/features/outlook/types";
import { useLeagueApi } from "@/lib/league";
import { eventMarks } from "./logic";
import type { SeasonEventRow } from "./types";

const KIND_LABEL = { trade: "Trade", injury: "Injury", big_week: "Big week" } as const;
const MISSING =
  "Marked: your trades, injuries to your starters (Sleeper's Out, IR or Doubtful, from the daily snapshots) and weeks far above your average. Not marked: waiver moves, and anything before the first saved run.";

function EventList({ events }: { events: readonly SeasonEventRow[] }) {
  if (events.length === 0) return <p className="mt-2 text-caption text-muted">Nothing to mark yet.</p>;
  return (
    <ul className="mt-2 text-caption">
      {events.map((e) => (
        <li key={`${e.kind}-${e.when}-${e.label}`} className="py-0.5">
          <span className="sr-only">{KIND_LABEL[e.kind]}: </span>{e.label}{" "}
          <span className="text-muted">{e.run_at === null ? "(before the first saved run)" : `(shown at the ${formatRunDate(e.run_at)} run)`}</span>
        </li>
      ))}
    </ul>
  );
}

/** The odds chart with my trades, starter injuries and big weeks marked on my line. */
export function SeasonOdds() {
  const odds = useLeagueApi<SeasonOddsRow[]>("season-odds");
  const history = useLeagueApi<OddsHistoryRow[]>("odds-history");
  const events = useLeagueApi<SeasonEventRow[]>("season-events");
  if (odds.kind !== "ready" || history.kind !== "ready") return null;
  if (!canShowHistory(odds.data, history.data)) return <p className="measure mb-8 text-caption text-muted">{HISTORY_WAIT_MESSAGE}</p>;
  const list = events.kind === "ready" ? events.data : [];
  return (
    <Section title="Playoff odds over the season" caption="Chance to make the playoffs after each saved run; your line is bold." howCalculated={MISSING}>
      <OddsHistoryChart odds={odds.data} history={history.data} marks={eventMarks(list).byRun} />
      <EventList events={list} />
    </Section>
  );
}
