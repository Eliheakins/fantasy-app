import { possessive } from "@/lib/text";
import type { ReactNode } from "react";
import { Section } from "@/components/Section";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
function Rows<T>({
  state,
  title,
  caption,
  howCalculated,
  children,
}: {
  state: ApiState<T[]>;
  title: string;
  caption: string;
  howCalculated?: ReactNode;
  children: (rows: T[]) => ReactNode;
}) {
  return (
    <Section title={title} caption={caption} howCalculated={howCalculated} level={3}>
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
  const owner = viewed?.team_name ? possessive(viewed.team_name) : "your";
  const tabs: { value: string; label: string; body: ReactNode }[] = [
    {
      value: "power",
      label: "Power rankings",
      body: (
        <Rows
          state={power}
          title="Power rankings"
          caption="Each team's expected score this week, from its best lineup."
          howCalculated="The week in progress counts points already scored. The bar is drawn from zero, so the gaps look smaller than the points."
        >
          {(rows) => <PowerRankings rows={rows} />}
        </Rows>
      ),
    },
    {
      value: "schedule",
      label: "Schedule strength",
      body: (
        <Rows
          state={power}
          title="Remaining schedule strength"
          caption="The average expected score of the opponents a team still plays. Rank 1 is the toughest schedule."
          howCalculated="Playoff odds are shown beside it for reference only; the schedule is one input to them, not the whole story."
        >
          {(rows) => <ScheduleStrength rows={rows} />}
        </Rows>
      ),
    },
    {
      value: "positional",
      label: "Positional strength",
      body: (
        <Rows
          state={teamGrades}
          title="Positional strength"
          caption="Points per week above a free agent, from the best lineup, graded by league rank. Tap a grade for the split."
          howCalculated="Bar length is the starters' points per week above a free-agent stand-in. Grades follow league rank: top fifth A, bottom fifth F. Weighted 75% starters, 25% bench depth."
        >
          {(r) => <PositionalStrength rows={r} />}
        </Rows>
      ),
    },
    {
      value: "luck",
      label: "Luck and all-play",
      body: (
        <Rows
          state={luck}
          title="Luck and all-play"
          caption="Luck is actual wins minus the wins the all-play record predicts. A plus means more wins than the team earned."
          howCalculated="All-play counts each week against every other team's score. Completed weeks only."
        >
          {(r) => <LuckTable rows={r} />}
        </Rows>
      ),
    },
    {
      value: "efficiency",
      label: "Lineup efficiency",
      body: (
        <Rows
          state={grades}
          title="Lineup efficiency"
          caption="Points started as a share of the best lineup that was on the roster, in hindsight."
          howCalculated="Completed weeks only. Best possible is the highest score the roster could have started each week."
        >
          {(r) => <GradesTable rows={r} />}
        </Rows>
      ),
    },
    {
      value: "whatif",
      label: "What if",
      body: (
        <Section
          level={3}
          title="What if"
          caption={`How ${owner} playoff and title odds change if one side of a matchup wins, in percentage points (pp).`}
        >
          <WhatIf />
        </Section>
      ),
    },
  ];
  return (
    <Section title="League details" caption="Every team in the league, one table at a time.">
      <Tabs defaultValue="power">
        <TabsList aria-label="League details" className="-mx-[var(--page-pad)] overflow-x-auto px-[var(--page-pad)] md:mx-0 md:px-0">
          {tabs.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="shrink-0">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.value} value={t.value} className="mt-6">
            {t.body}
          </TabsContent>
        ))}
      </Tabs>
    </Section>
  );
}
