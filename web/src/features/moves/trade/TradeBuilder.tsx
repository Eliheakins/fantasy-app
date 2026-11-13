import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Evaluator } from "./Evaluator";
import { useTradeScope } from "./useTradeScope";

/** Under Moves: the live trade builder. */
export function TradeBuilder() {
  const { league, scope } = useTradeScope();
  const partners = useEnvelopeQuery("/api/leagues/{league}/trade-partners", league === null ? null : { path: { league } });
  const mine = useEnvelopeQuery("/api/leagues/{league}/trade-assets", league === null ? null : { path: { league } });
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
