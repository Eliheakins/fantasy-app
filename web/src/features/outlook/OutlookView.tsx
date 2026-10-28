import type { ReactNode } from "react";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary, NoData } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useLeagueApi } from "@/lib/league";
import { OddsHistoryChart } from "./OddsHistoryChart";
import { OddsTable } from "./OddsTable";
import { ScheduleTable } from "./ScheduleTable";
import { SeedChart } from "./SeedChart";
import { HISTORY_WAIT_MESSAGE, canShowHistory } from "./logic";
import type { OddsHistoryRow, ScheduleRow, SeasonOddsRow, SeedRow } from "./types";
import { capitalize, useWho } from "./who";

/** Optional blocks show only when they have rows, as Streamlit does; an error says so. */
function Optional<T>({ state, children }: { state: ApiState<T[]>; children: (rows: T[]) => ReactNode }) {
  if (state.kind === "error") {
    return <p role="alert" className="mt-6 text-caption text-warning">Could not load this section: {state.error.message}</p>;
  }
  if (state.kind !== "ready" || state.data.length === 0) return null;
  return <>{children(state.data)}</>;
}

const ODDS_METHOD =
  "Simulated rest of season, 20,000 runs, assuming current rosters: no waiver moves, trades or new injuries beyond the usual spread of game outcomes. Kicker and defense use each team's own projection.";
const SCHEDULE_METHOD =
  "Expected points are each team's best lineup this week, with each team's own kicker and defense projection. The win chance is a quick normal approximation, not the full simulation.";

export function OutlookView() {
  const who = useWho();
  const odds = useLeagueApi<SeasonOddsRow[]>("season-odds");
  const seeds = useLeagueApi<SeedRow[]>("seeds");
  const schedule = useLeagueApi<ScheduleRow[]>("schedule");
  const history = useLeagueApi<OddsHistoryRow[]>("odds-history");
  return (
    <ApiBoundary state={odds}>
      {(oddsRows) =>
        oddsRows.length === 0 ? (
          <NoData />
        ) : (
          <>
            <Section title="Season odds" caption="Ranked by chance to make the playoffs." howCalculated={ODDS_METHOD}>
              <div className="max-w-4xl"><OddsTable rows={oddsRows} who={who} /></div>
            </Section>
            <Optional state={seeds}>
              {(rows) => (
                <Section
                  title={who.name ? `Where ${who.name} finishes` : "Where you finish"}
                  caption="Chance of each regular-season seed. Seeds 1 to 6 make the playoffs; 1 and 2 get a bye."
                >
                  <SeedChart rows={rows} />
                </Section>
              )}
            </Optional>
            <Optional state={schedule}>
              {(rows) => (
                <Section title={`${capitalize(who.your)} remaining schedule`} caption="Best-lineup points each side, and the chance to win." howCalculated={SCHEDULE_METHOD}>
                  <div className="max-w-4xl"><ScheduleTable rows={rows} who={who} /></div>
                </Section>
              )}
            </Optional>
            {history.kind === "ready" && canShowHistory(oddsRows, history.data) ? (
              <Section
                title="Season odds, all teams"
                caption={`Chance to make the playoffs after each saved run. ${who.name ?? "Your team"} is the bold line.`}
              >
                <OddsHistoryChart odds={oddsRows} history={history.data} />
              </Section>
            ) : (
              <p className="measure mt-8 text-caption text-muted">{HISTORY_WAIT_MESSAGE}</p>
            )}
          </>
        )
      }
    </ApiBoundary>
  );
}
