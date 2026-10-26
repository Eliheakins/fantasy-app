import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { actionGain, actionSentence } from "@/features/home/logic";
import { useLeagueApi } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { Delta } from "@/viz";
import { AsOf, Ideas } from "./Ideas";
import { nextLineupAction } from "./logic";
import { LastWeek, OddsChange, Performance } from "./Results";
import type { ActionRow, DigestData } from "./types";

function NextAction() {
  const actions = useLeagueApi<ActionRow[]>("actions?stored_adds=true");
  return (
    <ApiBoundary state={actions}>
      {(rows) => {
        const next = nextLineupAction(rows);
        if (next === null) return <p className="text-body text-muted">Nothing to change in the lineup right now.</p>;
        const gain = actionGain(next);
        return (
          <div className="card-flat">
            <div className="text-caption font-semibold text-muted">{next.kind}</div>
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span>{actionSentence(next.text)}</span>
              {gain !== null && (
                <span className="whitespace-nowrap">
                  <Delta points={gain} /> <span className="text-caption text-muted">points</span>
                </span>
              )}
            </div>
          </div>
        );
      }}
    </ApiBoundary>
  );
}

function Body({ data }: { data: DigestData }) {
  const { viewed } = useTeam();
  const lastWeek = data.last_week?.week;
  return (
    <div>
      <Section title="Last week" caption="The result, the points left on the bench and how lucky the result was.">
        <LastWeek row={data.last_week} currentWeek={data.ideas.current_week} />
      </Section>
      <Section
        title="Against projection"
        caption={`Starters${lastWeek ? ` in week ${lastWeek}` : ""}: points scored minus the projection saved before the game. Skill positions only.`}
        howCalculated="The projection is the last one saved for the player that week, from the learned or baseline model set in config, before the Sleeper blend and injury adjustments. It is not the number the app showed. Projections were only saved from week 7, so earlier weeks have none. The bar starts at the centre line: left is under the projection, right is over, scaled to the biggest miss."
      >
        <Performance rows={data.performance} />
      </Section>
      <Section
        title="Season odds change"
        caption="Playoff and title odds in the latest run against the last run of an earlier week, in percentage points."
        howCalculated="Each refresh saves a run. Several refreshes in one week count once, as the last of that week. With no earlier week saved, the change reads 'no earlier run', not zero."
      >
        <OddsChange rows={data.odds_change} mineLabel={viewed === null} />
      </Section>
      <Section
        title="Top waiver adds"
        caption="Free agents who add the most points over the rest of the season, from the last refresh."
        howCalculated="Each add is simulated against the player it would replace, over the rest of the season. Changes inside the simulation error show as ~."
      >
        <AsOf info={data.ideas} />
        <Ideas kind="waiver" rows={data.waivers} info={data.ideas} />
      </Section>
      <Section
        title="Trade ideas"
        caption="Trades that fill both teams' positions of need, from the last refresh."
        howCalculated="Found over every roster in the league, so they are saved at refresh rather than found when the page opens."
      >
        <Ideas kind="trade" rows={data.trades} info={data.ideas} />
      </Section>
      <Section title="Next lineup action" caption="The most useful lineup change right now.">
        <NextAction />
      </Section>
    </div>
  );
}

/** The weekly digest for the selected league: every number comes from the digest route. */
export function DigestView() {
  const digest = useLeagueApi<DigestData>("digest");
  return <ApiBoundary state={digest}>{(data) => <Body data={data} />}</ApiBoundary>;
}
