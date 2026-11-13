import { useCallback } from "react";
import { useSearchParams } from "react-router";
import { Callout } from "@/components/Callout";
import { PageHeader } from "@/components/PageHeader";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { MoveList } from "@/features/moves/MoveList";
import { MOVE_NOISE_PERCENT, type MoveView, filterMoves, moveHeadline, worthMove } from "@/features/moves/moves";
import { OUT_MESSAGE, SEASON_OVER, isDone } from "@/features/effects/phase";
import { useMoves } from "@/features/moves/useMoves";
import { EffectText } from "@/features/effects/EffectText";
import { posOf } from "@/features/moves/waivers/logic";
import { type WaiverParams, WaiversContent } from "@/features/moves/waivers/WaiversView";
import { deadlineWeekState } from "@/lib/deadline";
import { useLeague, useLeagueRow } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { useHeld } from "@/lib/useHeld";
import { useSearchParam } from "@/lib/useSearchParam";
import { usePageEyebrow } from "@/lib/week";
import { TradeBuilder } from "@/features/moves/trade/TradeBuilder";
import { TradeDetails } from "@/features/moves/trade/TradeDetails";

const VIEWS = [
  { value: "all", label: "All" },
  { value: "fa", label: "Free agents" },
  { value: "trades", label: "Trades" },
] as const;

const EMPTY: Record<MoveView, string> = {
  all: "No free agent or trade idea raises your odds right now.",
  fa: "No free agent worth adding.",
  trades: "No trade ideas right now.",
};

const viewOf = (raw: string | null): MoveView => (raw === "fa" || raw === "trades" ? raw : "all");

/** The waiver tables' ranking (`?rank=playoffs`, else rest of season) and position filter (`?pos=`), from the URL. */
function useWaiverParams(): WaiverParams {
  const [rawRank, setRawRank] = useSearchParam("rank");
  const [rawPos, setPos] = useSearchParam("pos");
  const onRank = useCallback<WaiverParams["onRank"]>((next) => setRawRank(next === "ros" ? null : next), [setRawRank]);
  const onShowAll = useCallback(() => setPos(null), [setPos]);
  return { rank: rawRank === "playoffs" ? "playoffs" : "ros", onRank, pos: posOf(rawPos), onShowAll };
}

/**
 * Moves: one ranked list of free agent adds and trade ideas (?view=fa|trades filters it), the live trade
 * builder under it, and the full tables in a closed disclosure.
 */
export default function Moves() {
  const [params, setParams] = useSearchParams();
  const view = viewOf(params.get("view"));
  const waiverParams = useWaiverParams();
  const eyebrow = usePageEyebrow("Moves");
  const { addsPending, tradesPending, moves, addsError, tradesFailed, phase } = useMoves();
  const done = isDone(phase);
  const top = moves[0];
  const choose = (next: string) => {
    if (!next) return; // clicking the selected item would clear a single-select group
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev);
        out.set("view", next);
        return out;
      },
      { replace: true },
    );
  };
  const showAdds = view !== "trades"; // a part the view does not show never blocks it
  const showTrades = view !== "fa";
  const pending = addsPending || tradesPending;
  const listPending = (showAdds && addsPending) || (showTrades && tradesPending);
  const failed = [addsError !== null && "free agents", tradesFailed && "trade ideas"].filter(Boolean);
  // a background refetch must not unmount the number the reader has open
  const { league } = useLeague();
  const row = useLeagueRow();
  const title = done
    ? phase === "out"
      ? OUT_MESSAGE
      : (row?.playoff_label ?? SEASON_OVER)
    : pending
      ? "Looking for your best move…"
      : failed.length === 2
        ? "Moves did not load"
        : moveHeadline(top, failed.length > 0);
  const answer =
    !done && top && worthMove(top) && !pending ? <EffectText todo={top} playoffNoise={MOVE_NOISE_PERCENT} inline /> : undefined;
  const closing =
    deadlineWeekState(row?.current_week, row?.trade_deadline, row?.playoff_week_start == null ? null : row.playoff_week_start - 1) ===
    "closing";
  const { team } = useTeam();
  const header = useHeld({ title, answer }, pending, `${league}|${team}`);
  return (
    <div className="flex flex-col">
      <PageHeader title={header.title} eyebrow={eyebrow} answer={header.answer} />
      {closing && (
        <Callout variant="warn" className="mb-4">
          Trades close after week {row?.trade_deadline}.
        </Callout>
      )}
      <section aria-labelledby="moves-heading" className="mb-8 key-panel">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="moves-heading" className="text-section font-semibold">
            Moves, best first
          </h2>
          <ToggleGroup type="single" aria-label="Moves view" value={view} onValueChange={choose}>
            {VIEWS.map((v) => (
              <ToggleGroupItem key={v.value} value={v.value}>
                {v.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        {done ? (
          <p className="text-body">{phase === "out" ? `${OUT_MESSAGE}: no add or trade changes your title odds.` : `${SEASON_OVER}.`}</p>
        ) : listPending && moves.length === 0 ? (
          <p role="status" className="text-muted">
            Simulating your moves…
          </p>
        ) : (
          <MoveList moves={filterMoves(moves, view)} empty={EMPTY[view]} />
        )}
        {showAdds && addsError !== null && (
          <p role="alert" className="mt-3 text-caption text-warning">
            The free agent list did not load: {addsError}
          </p>
        )}
        {showTrades && tradesFailed && (
          <p role="alert" className="mt-3 text-caption text-warning">
            Trade ideas did not load.
          </p>
        )}
        <p className="measure mt-3 text-caption text-muted">
          Ordered by {phase === "playoffs" ? "title" : "playoff"}-odds change first, then fantasy points; the two are not converted. Points
          are net of the drop. Trade ideas are your stored finds; build any other trade below.
        </p>
      </section>
      <TradeBuilder />
      <details className="mt-8 border-t border-line pt-2">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-section font-semibold">Details</summary>
        <div className="flex flex-col gap-8 pt-4">
          <WaiversContent {...waiverParams} />
          <TradeDetails />
        </div>
      </details>
    </div>
  );
}
