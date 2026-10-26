import { ApiBoundary } from "@/components/ApiBoundary";
import { useApi } from "@/hooks/useApi";
import { Confidence, DataTableFallback, Delta, RangeBar, formatNumber, formatPercent, sharedDomain } from "@/viz";
import { Block, Stat } from "./parts";
import { leagueUrl } from "./hooks";
import {
  type ActionRow, type WinProbability,
  actionGain, actionSentence, actionShare, myRange, opponentRange, winChance, worthActing,
} from "./logic";

const BAR_WIDTH = 240;
const BAR_HEIGHT = 24;

function RangeRow({ label, p10, p50, p90, domain }: {
  label: string; p10: number; p50: number; p90: number; domain: NonNullable<ReturnType<typeof sharedDomain>>;
}) {
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-0 @md:grid-cols-[5.5rem_minmax(0,1fr)_9rem]">
      <span className="text-body">{label}</span>
      <div className="[&>svg]:h-auto [&>svg]:w-full">
        <RangeBar p10={p10} p50={p50} p90={p90} domain={domain} width={BAR_WIDTH} height={BAR_HEIGHT} />
      </div>
      <span className="col-start-2 text-caption text-muted tabular-nums @md:col-start-3">
        {formatNumber(p10)} to {formatNumber(p90)}, median {formatNumber(p50)}
      </span>
    </div>
  );
}

function RangeBars({ odds, mine }: { odds: WinProbability; mine: boolean }) {
  const me = myRange(odds);
  const them = opponentRange(odds);
  const domain = me && them ? sharedDomain([me, them]) : null;
  if (!me || !them || !domain) return null;
  const ownLabel = mine ? "You" : "This team";
  return (
    <div className="space-y-2">
      <RangeRow label={ownLabel} {...me} domain={domain} />
      <RangeRow label="Opponent" {...them} domain={domain} />
      <p className="text-caption text-muted">Bars show where 80% of outcomes land (10th to 90th percentile); the tick is the median.</p>
      <DataTableFallback
        columns={["Team", "Low (10%)", "Median", "High (90%)"]}
        rows={[
          [ownLabel, formatNumber(me.p10), formatNumber(me.p50), formatNumber(me.p90)],
          ["Opponent", formatNumber(them.p10), formatNumber(them.p50), formatNumber(them.p90)],
        ]}
      />
    </div>
  );
}

function ActionList({ actions, odds, mine, teamName }: {
  actions: ActionRow[]; odds: WinProbability | null; mine: boolean; teamName: string;
}) {
  const shown = actions.filter((a) => worthActing(a, actionShare(a, odds)));
  if (shown.length === 0) {
    return <p className="text-muted">Nothing stands out: {mine ? "your" : `${teamName}'s`} lineup is set and no add moves the odds.</p>;
  }
  return (
    <ol className="space-y-3">
      {shown.map((a) => {
        const gain = actionGain(a);
        const share = actionShare(a, odds);
        return (
          <li key={`${a.kind}-${a.text}`}>
            <div className="text-caption font-semibold text-muted">{a.kind}</div>
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span>{actionSentence(a.text)}</span>
              {gain !== null && (
                <span className="whitespace-nowrap">
                  <Delta points={gain} /> <span className="text-caption text-muted">points</span>
                </span>
              )}
              {share !== null && <Confidence share={share} />}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** This week's win chance and ranges, then the moves worth making. */
export function Advice({ leagueKey, mine, teamName }: { leagueKey: string; mine: boolean; teamName: string }) {
  const odds = useApi<WinProbability>(leagueUrl(leagueKey, "win-probability"));
  const actions = useApi<ActionRow[]>(leagueUrl(leagueKey, "actions"));
  const oddsData = odds.kind === "ready" ? odds.data : null;
  const chance = oddsData ? winChance(oddsData) : null;
  return (
    <>
      <ApiBoundary state={odds}>
        {(d) => (
          <Block title="This week">
            {chance !== null && <Stat label="Chance to win this week" value={formatPercent(chance)} />}
            <div className="mt-3"><RangeBars odds={d} mine={mine} /></div>
          </Block>
        )}
      </ApiBoundary>
      <Block title="Do this now">
        <ApiBoundary state={actions}>
          {(a) => <ActionList actions={a} odds={oddsData} mine={mine} teamName={teamName} />}
        </ApiBoundary>
      </Block>
    </>
  );
}
