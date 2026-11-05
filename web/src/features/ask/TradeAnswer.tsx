import { Link, useLocation } from "react-router-dom";

import { ApiBoundary } from "@/components/ApiBoundary";
import { Callout } from "@/components/Callout";
import { navSearch } from "@/components/layout/navLinks";
import { FailureNotice } from "@/features/trades/FailureNotice";
import { tradeKey } from "@/features/trades/logic";
import { TradeResult } from "@/features/trades/TradeResult";
import type { TradeEvaluation, TradeRequest } from "@/features/trades/types";
import { usePostApi } from "@/features/trades/usePostApi";
import { useLeague, useLeagueApi } from "@/lib/league";
import type { components } from "@/api/schema";

import { planTrade, type TradeOutcome, tradeSummary } from "./tradeAsk";

type Owners = components["schemas"]["OwnersData"];
interface Props extends Pick<TradeOutcome, "give" | "get"> {
  /** Display names by gsis id, from the question's player matches. */
  names: Readonly<Record<string, string>>;
  positions: Readonly<Record<string, string | null>>;
}

/** A trade question answered by the Trades page's own evaluation, for the partner who owns the get side. */
export function TradeAnswer(props: Props) {
  const owners = useLeagueApi<Owners>("owners");
  const { pathname, search } = useLocation();
  const tradesLink = `/trades${navSearch("/trades", search, pathname)}`;
  return (
    <section aria-label="Trade" className="space-y-3 border-t border-border pt-3">
      <ApiBoundary state={owners}>
        {(o) => <Plan {...props} owners={o.rows} tradesLink={tradesLink} />}
      </ApiBoundary>
      <p className="text-caption text-muted">
        <Link to={tradesLink} className="font-medium text-text underline-offset-2 hover:underline">
          Open the Trades page
        </Link>{" "}
        to change the players or look for other trades.
      </p>
    </section>
  );
}

function Plan({ owners, tradesLink, ...trade }: Props & { owners: Owners["rows"]; tradesLink: string }) {
  const plan = planTrade(trade, trade.names, owners, trade.positions);
  if (plan.kind === "handoff") {
    return (
      <Callout variant="info">
        {plan.text} Build this trade on the{" "}
        <Link to={tradesLink} className="underline">Trades page</Link>.
      </Callout>
    );
  }
  return <Evaluation request={plan.request} />;
}

function Evaluation({ request }: { request: TradeRequest }) {
  const { league } = useLeague();
  const { state, refetch } = usePostApi<TradeEvaluation>(
    ["ask-trade", tradeKey({ partner: request.partner_roster_id, give: request.give_ids, get: request.get_ids })],
    `/api/leagues/${encodeURIComponent(league ?? "")}/trades/evaluate`,
    request,
  );
  if (state?.kind === "loading" || state === null) return <p role="status" className="text-muted">Simulating the trade…</p>;
  if (state.kind === "error") return <FailureNotice error={state.error} onRetry={refetch} />;
  return <ApiBoundary state={state}>{(result) => <Result result={result} />}</ApiBoundary>;
}

function Result({ result }: { result: TradeEvaluation }) {
  const me = result.odds.find((s) => s.side === "me");
  return (
    <div className="space-y-3">
      {me && <p className="text-body font-semibold text-text">{tradeSummary(me)}</p>}
      <TradeResult result={result} />
    </div>
  );
}
