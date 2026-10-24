import { ApiBoundary } from "@/components/ApiBoundary";
import { Evaluator } from "@/features/trades/Evaluator";
import { FindTradesSection } from "@/features/trades/FindTrades";
import { StrengthSection } from "@/features/trades/StrengthSection";
import type { Asset, Partner } from "@/features/trades/types";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";

export default function Trades() {
  const { league } = useLeague();
  const base = league === null ? null : `/api/leagues/${encodeURIComponent(league)}`;
  const partners = useApi<Partner[]>(base && `${base}/trade-partners`);
  const mine = useApi<Asset[]>(base && `${base}/trade-assets`);
  return (
    <section className="space-y-6">
      <h1 className="text-display font-semibold">Trades</h1>
      {league !== null && (
        <>
          <StrengthSection />
          <FindTradesSection key={league} league={league} />
          <ApiBoundary state={partners}>
            {(ps) => (
              <ApiBoundary state={mine}>
                {(assets) => <Evaluator key={league} league={league} partners={ps} mine={assets} />}
              </ApiBoundary>
            )}
          </ApiBoundary>
        </>
      )}
    </section>
  );
}
