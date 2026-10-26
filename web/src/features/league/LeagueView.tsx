import type { ReactNode } from "react";
import { Section } from "@/components/Section";
import { useTeam } from "@/lib/teamContext";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { useLeagueApi } from "@/lib/league";
import { GradesTable, LuckTable } from "./LuckAndGrades";
import { PowerRankings, ScheduleStrength } from "./PowerRankings";
import { PositionalStrength } from "./PositionalStrength";
import { WhatIf } from "./WhatIf";
import type { LuckRow, ManagerGradeRow, PowerRankingRow, TeamGradeRow } from "./types";

/** A table section that loads on its own; an empty result says so instead of vanishing. */
function Rows<T>({ state, title, caption, howCalculated, children }: {
  state: ApiState<T[]>;
  title: string;
  caption: string;
  howCalculated?: ReactNode;
  children: (rows: T[]) => ReactNode;
}) {
  return (
    <Section title={title} caption={caption} howCalculated={howCalculated}>
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
  const teamGrades = useLeagueApi<TeamGradeRow[]>("team-grades");
  const { viewed } = useTeam();
  const owner = viewed ? `${viewed.team_name}'s` : "your";
  return (
    <div>
      <Rows
        state={power}
        title="Power rankings"
        caption="Each team's expected score this week, from its best lineup."
        howCalculated="The week in progress counts points already scored. The bar is drawn from zero, so the gaps look smaller than the points."
      >
        {(rows) => <PowerRankings rows={rows} />}
      </Rows>
      <Rows
        state={power}
        title="Remaining schedule strength"
        caption="The average expected score of the opponents a team still plays. Rank 1 is the toughest schedule."
        howCalculated="Playoff odds are shown beside it for reference only; the schedule is one input to them, not the whole story."
      >
        {(rows) => <ScheduleStrength rows={rows} />}
      </Rows>
      <Rows
        state={teamGrades}
        title="Positional strength"
        caption="Points per week above a free agent, from the best lineup, graded by league rank. Tap a grade for the split."
        howCalculated="Bar length is the starters' points per week above a free-agent stand-in. Grades follow league rank: top fifth A, bottom fifth F. Weighted 75% starters, 25% bench depth."
      >
        {(r) => <PositionalStrength rows={r} />}
      </Rows>
      <Rows
        state={luck}
        title="Luck and all-play"
        caption="Luck is actual wins minus the wins the all-play record predicts. A plus means more wins than the team earned."
        howCalculated="All-play counts each week against every other team's score. Completed weeks only."
      >
        {(r) => <LuckTable rows={r} />}
      </Rows>
      <Rows
        state={grades}
        title="Lineup efficiency"
        caption="Points started as a share of the best lineup that was on the roster, in hindsight."
        howCalculated="Completed weeks only. Best possible is the highest score the roster could have started each week."
      >
        {(r) => <GradesTable rows={r} />}
      </Rows>
      <Section
        title="What if"
        caption={`How ${owner} playoff and title odds change if one side of a matchup wins, in percentage points (pp).`}
      >
        <WhatIf />
      </Section>
    </div>
  );
}
