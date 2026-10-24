import type { ReactNode } from "react";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary, NoData } from "@/components/ApiBoundary";
import { useLeagueApi } from "@/lib/league";
import { OddsHistoryChart } from "./OddsHistoryChart";
import { OddsTable } from "./OddsTable";
import { ScheduleTable } from "./ScheduleTable";
import { SeedChart } from "./SeedChart";
import { HISTORY_WAIT_MESSAGE, canShowHistory } from "./logic";
import type { OddsHistoryRow, ScheduleRow, SeasonOddsRow, SeedRow } from "./types";

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="text-body font-semibold">{title}</h2>
      {note && <p className="mb-2 text-caption text-muted">{note}</p>}
      {children}
    </section>
  );
}

/** Optional blocks show only when they have rows, as Streamlit does; an error says so. */
function Optional<T>({ state, children }: { state: ApiState<T[]>; children: (rows: T[]) => ReactNode }) {
  if (state.kind === "error") return <p className="mt-6 text-caption text-muted">Could not load this section: {state.error.message}</p>;
  if (state.kind !== "ready" || state.data.length === 0) return null;
  return <>{children(state.data)}</>;
}

export function OutlookView() {
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
            <p className="mb-2 text-caption text-muted">
              Simulated rest of season, 20,000 runs, assuming current rosters: no waiver moves, trades or new injuries
              beyond the usual spread of game outcomes. Defenses are a league average for now.
            </p>
            <OddsTable rows={oddsRows} />
            <Optional state={seeds}>
              {(rows) => (
                <Section title="Where you finish" note="Chance of each regular-season seed. Seeds 1 to 6 make the playoffs, 1 and 2 get byes.">
                  <SeedChart rows={rows} />
                </Section>
              )}
            </Optional>
            <Optional state={schedule}>
              {(rows) => (
                <Section
                  title="Your remaining schedule"
                  note="Expected points are each team's best lineup this week, with K and DEF at league averages. The win chance is a quick normal approximation, not the full simulation."
                >
                  <ScheduleTable rows={rows} />
                </Section>
              )}
            </Optional>
            {history.kind === "ready" && canShowHistory(oddsRows, history.data) ? (
              <Section title="Your odds over saved runs">
                <OddsHistoryChart odds={oddsRows} history={history.data} />
              </Section>
            ) : (
              <p className="mt-6 text-caption text-muted">{HISTORY_WAIT_MESSAGE}</p>
            )}
          </>
        )
      }
    </ApiBoundary>
  );
}
