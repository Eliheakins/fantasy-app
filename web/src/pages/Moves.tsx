import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { MoveList } from "@/features/moves/MoveList";
import { MOVE_NOISE_PERCENT, type MoveView, filterMoves, moveHeadline, worthMove } from "@/features/moves/moves";
import { useMoves } from "@/features/moves/useMoves";
import { EffectText } from "@/features/effects/EffectText";
import { WaiversContent } from "@/features/moves/waivers/WaiversView";
import { useLeague } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { useHeld } from "@/lib/useHeld";
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

/**
 * Moves: one ranked list of free agent adds and trade ideas (?view=fa|trades filters it), the live trade
 * builder under it, and the full tables in a closed disclosure.
 */
export default function Moves() {
  const [params, setParams] = useSearchParams();
  const view = viewOf(params.get("view"));
  const eyebrow = usePageEyebrow("Moves");
  const { addsPending, tradesPending, moves, addsError, tradesFailed } = useMoves();
  const top = moves[0];
  const choose = (next: string) => {
    if (!next) return; // clicking the selected item would clear a single-select group
    setParams((prev) => {
      const out = new URLSearchParams(prev);
      out.set("view", next);
      return out;
    }, { replace: true });
  };
  const showAdds = view !== "trades"; // a part the view does not show never blocks it
  const showTrades = view !== "fa";
  const pending = addsPending || tradesPending;
  const listPending = (showAdds && addsPending) || (showTrades && tradesPending);
  const failed = [addsError !== null && "free agents", tradesFailed && "trade ideas"].filter(Boolean);
  const title = pending ? "Looking for your best move…" : failed.length === 2 ? "Moves did not load" : moveHeadline(top, failed.length > 0);
  const answer = top && worthMove(top) && !pending ? <EffectText todo={top} playoffNoise={MOVE_NOISE_PERCENT} inline /> : undefined;
  // a background refetch must not unmount the number the reader has open
  const { league } = useLeague();
  const { team } = useTeam();
  const header = useHeld({ title, answer }, pending, `${league}|${team}`);
  return (
    <div className="flex flex-col">
      <PageHeader title={header.title} eyebrow={eyebrow} answer={header.answer} />
      <section aria-labelledby="moves-heading" className="mb-8 key-panel">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="moves-heading" className="text-section font-semibold">Moves, best first</h2>
          <ToggleGroup type="single" aria-label="Moves view" value={view} onValueChange={choose}>
            {VIEWS.map((v) => (
              <ToggleGroupItem key={v.value} value={v.value}>{v.label}</ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        {listPending && moves.length === 0 ? (
          <p role="status" className="text-muted">Simulating your moves…</p>
        ) : (
          <MoveList moves={filterMoves(moves, view)} empty={EMPTY[view]} />
        )}
        {showAdds && addsError !== null && <p role="alert" className="mt-3 text-caption text-warning">The free agent list did not load: {addsError}</p>}
        {showTrades && tradesFailed && <p role="alert" className="mt-3 text-caption text-warning">Trade ideas did not load.</p>}
        <p className="measure mt-3 text-caption text-muted">
          Ordered by playoff-odds change first, then fantasy points; the two are not converted. Points are net of the drop.
          Trade ideas are your stored finds; build any other trade below.
        </p>
      </section>
      <TradeBuilder />
      <details className="mt-8 border-t border-line pt-2">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-section font-semibold">Details</summary>
        <div className="flex flex-col gap-8 pt-4">
          <WaiversContent />
          <TradeDetails />
        </div>
      </details>
    </div>
  );
}
