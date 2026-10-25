import type { ReactNode } from "react";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary, NoData } from "@/components/ApiBoundary";
import { useLeagueApi } from "@/lib/league";
import { GradesTable, LuckTable } from "./LuckAndGrades";
import { PowerRankings, ScheduleStrength } from "./PowerRankings";
import { WhatIf } from "./WhatIf";
import type { LuckRow, ManagerGradeRow, PowerRankingRow } from "./types";

function Section({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="text-body font-semibold">{title}</h2>
      <p className="mb-2 text-caption text-muted">{note}</p>
      {children}
    </section>
  );
}

/** A table section that loads on its own; an empty result says so instead of vanishing. */
function Rows<T>({ state, title, note, children }: {
  state: ApiState<T[]>;
  title: string;
  note: string;
  children: (rows: T[]) => ReactNode;
}) {
  return (
    <Section title={title} note={note}>
      <ApiBoundary state={state}>
        {(rows) => (rows.length === 0 ? <p className="text-body text-muted">Nothing to show yet.</p> : children(rows))}
      </ApiBoundary>
    </Section>
  );
}

export function LeagueView() {
  const power = useLeagueApi<PowerRankingRow[]>("power-rankings");
  const luck = useLeagueApi<LuckRow[]>("luck");
  const grades = useLeagueApi<ManagerGradeRow[]>("manager-grades");
  return (
    <ApiBoundary state={power}>
      {(rows) =>
        rows.length === 0 ? (
          <NoData />
        ) : (
          <>
            <Section
              title="Power rankings"
              note="Each team's expected score this week, from its best lineup. The week in progress counts points already scored."
            >
              <PowerRankings rows={rows} />
            </Section>
            <Section
              title="Remaining schedule strength"
              note="The average expected score of the opponents a team still plays. Rank 1 is the toughest remaining schedule."
            >
              <ScheduleStrength rows={rows} />
            </Section>
            <Rows
              state={luck}
              title="Luck and all-play"
              note="All-play counts each week against every other team's score. Luck is actual wins minus the wins that record predicts. Completed weeks only."
            >
              {(r) => <LuckTable rows={r} />}
            </Rows>
            <Rows
              state={grades}
              title="Manager grades"
              note="Efficiency is points started over the best lineup that was on the roster, in hindsight. Completed weeks only."
            >
              {(r) => <GradesTable rows={r} />}
            </Rows>
            <Section
              title="What if"
              note="Your playoff and title odds if one side of a matchup wins, in percentage points against your current odds."
            >
              <WhatIf />
            </Section>
          </>
        )
      }
    </ApiBoundary>
  );
}
