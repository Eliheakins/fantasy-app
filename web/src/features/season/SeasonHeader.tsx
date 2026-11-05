import { PageHeader } from "@/components/PageHeader";
import type { DigestData } from "@/features/digest/types";
import type { SeasonOddsRow } from "@/features/outlook/types";
import { useWho } from "@/features/outlook/who";
import { useLeague, useLeagueApi } from "@/lib/league";
import { useHeld } from "@/lib/useHeld";
import { Explain, ExplainDelta, NOISE_PERCENT, formatPercent } from "@/viz";

const TITLE_WAITING = "Season";
const SIM_WHY = "Share of the stored simulated seasons in which your team earns this, from the latest saved run. Playoff odds, bye and title come from the same seasons.";
const changeWhy = (week: number | undefined, prev: number | null | undefined) =>
  `Your playoff chance in the latest saved run${week === undefined ? "" : ` (as of week ${week})`} minus the previous saved run${prev == null ? "" : ` (as of week ${prev})`}. Percentage points.`;

/** h1 = the playoff odds; the sentence adds the week's change, the bye and the title chance. */
export function SeasonHeader({ eyebrow }: { eyebrow: string }) {
  const who = useWho();
  const odds = useLeagueApi<SeasonOddsRow[]>("season-odds");
  const digest = useLeagueApi<DigestData>("digest");
  const { league } = useLeague();
  const mine = odds.kind === "ready" ? odds.data.find((r) => r.is_me) : undefined;
  const changeRow = digest.kind === "ready" ? digest.data.odds_change.find((r) => r.is_me) : undefined;
  const change = changeRow?.d_playoffs;
  const header = mine ? (
    <PageHeader
      title={`${who.name ? `${who.name}: ` : ""}${formatPercent(mine.p_playoffs)} to make the playoffs`}
      eyebrow={eyebrow}
      answer={
        <>
          {change != null && <><ExplainDelta points={change * 100} noise={NOISE_PERCENT} why={changeWhy(changeRow?.as_of_week, changeRow?.prev_as_of_week)} /> <span className="text-muted">pp since the last week's run.</span>{" "}</>}
          A bye is <Explain why={SIM_WHY}>{formatPercent(mine.p_bye)}</Explain> and the title <Explain why={SIM_WHY}>{formatPercent(mine.p_title)}</Explain>.
        </>
      }
    />
  ) : (
    <PageHeader title={TITLE_WAITING} eyebrow={eyebrow} />
  );
  // a refetch must not unmount the numbers the reader has open
  return useHeld(header, !mine, String(league));
}
