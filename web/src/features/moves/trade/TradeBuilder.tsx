import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Evaluator } from "./Evaluator";
import type { Asset, Partner } from "./types";
import { useTradeScope } from "./useTradeScope";

/** Under Moves: the live trade builder. */
export function TradeBuilder() {
  const { league, scope, base } = useTradeScope();
  const partners = useEnvelopeQuery<Partner[]>(base && `${base}/trade-partners`);
  const mine = useEnvelopeQuery<Asset[]>(base && `${base}/trade-assets`);
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
