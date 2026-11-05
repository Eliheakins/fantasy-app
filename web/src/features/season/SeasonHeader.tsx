import { PageHeader } from "@/components/PageHeader";
import type { DigestData } from "@/features/digest/types";
import type { SeasonOddsRow } from "@/features/outlook/types";
import { useWho } from "@/features/outlook/who";
import { useLeagueApi } from "@/lib/league";
import { Delta, NOISE_PERCENT, formatPercent } from "@/viz";

const TITLE_WAITING = "Season";

/** h1 = the playoff odds; the sentence adds the week's change, the bye and the title chance. */
export function SeasonHeader({ eyebrow }: { eyebrow: string }) {
  const who = useWho();
  const odds = useLeagueApi<SeasonOddsRow[]>("season-odds");
  const digest = useLeagueApi<DigestData>("digest");
  const mine = odds.kind === "ready" ? odds.data.find((r) => r.is_me) : undefined;
  if (!mine) return <PageHeader title={TITLE_WAITING} eyebrow={eyebrow} />;
  const change = digest.kind === "ready" ? digest.data.odds_change.find((r) => r.is_me)?.d_playoffs : null;
  const title = `${who.name ? `${who.name}: ` : ""}${formatPercent(mine.p_playoffs)} to make the playoffs`;
  return (
    <PageHeader
      title={title}
      eyebrow={eyebrow}
      answer={
        <>
          {change != null && <><Delta points={change * 100} noise={NOISE_PERCENT} /> <span className="text-muted">pp since the last week's run.</span>{" "}</>}
          A bye is {formatPercent(mine.p_bye)} and the title {formatPercent(mine.p_title)}.
        </>
      }
    />
  );
}
