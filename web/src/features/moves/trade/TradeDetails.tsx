import { FindTradesSection } from "./FindTrades";
import { StrengthSection } from "./StrengthSection";
import { useTradeScope } from "./useTradeScope";

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
