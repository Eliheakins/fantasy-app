import { ApiBoundary } from "@/components/ApiBoundary";
import { Evaluator } from "@/features/trades/Evaluator";
import { FindTradesSection } from "@/features/trades/FindTrades";
import { StrengthSection } from "@/features/trades/StrengthSection";
import type { Asset, Partner } from "@/features/trades/types";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";

/** League, viewed team and API base; drafts and finder results belong to one team. */
function useTradeScope() {
  const { league } = useLeague();
  const { team } = useTeam();
  return { league, scope: `${league}:${team ?? "mine"}`, base: league === null ? null : `/api/leagues/${encodeURIComponent(league)}` };
}

/** Under Moves: the live trade builder. */
export default function Trades() {
  const { league, scope, base } = useTradeScope();
  const partners = useApi<Partner[]>(base && `${base}/trade-partners`);
  const mine = useApi<Asset[]>(base && `${base}/trade-assets`);
  if (league === null) return null;
  return (
    <ApiBoundary state={partners}>
      {(ps) => (
        <ApiBoundary state={mine}>
          {(assets) => <Evaluator key={scope} league={league} scope={scope} partners={ps} mine={assets} />}
        </ApiBoundary>
      )}
    </ApiBoundary>
  );
}

/** Under Moves, in the details: roster strength and the trade finder. */
export function TradeDetails() {
  const { league, scope } = useTradeScope();
  if (league === null) return null;
  return (
    <>
      <StrengthSection />
      <FindTradesSection key={scope} league={league} scope={scope} />
    </>
  );
}
