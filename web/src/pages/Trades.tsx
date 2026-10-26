import { PageHeader } from "@/components/PageHeader";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Evaluator } from "@/features/trades/Evaluator";
import { FindTradesSection } from "@/features/trades/FindTrades";
import { StrengthSection } from "@/features/trades/StrengthSection";
import type { Asset, Partner } from "@/features/trades/types";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";

export default function Trades() {
  const { league } = useLeague();
  const { team } = useTeam();
  const scope = `${league}:${team ?? "mine"}`; // drafts and finder results belong to one team
  const base = league === null ? null : `/api/leagues/${encodeURIComponent(league)}`;
  const partners = useApi<Partner[]>(base && `${base}/trade-partners`);
  const mine = useApi<Asset[]>(base && `${base}/trade-assets`);
  return (
    <div>
      <PageHeader title="Trades" />
      {league !== null && (
        <>
          <StrengthSection />
          <FindTradesSection key={scope} league={league} scope={scope} />
          <ApiBoundary state={partners}>
            {(ps) => (
              <ApiBoundary state={mine}>
                {(assets) => <Evaluator key={scope} league={league} scope={scope} partners={ps} mine={assets} />}
              </ApiBoundary>
            )}
          </ApiBoundary>
        </>
      )}
    </div>
  );
}
