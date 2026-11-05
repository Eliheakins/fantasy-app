import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { MoveList } from "@/features/moves/MoveList";
import { type MoveView, filterMoves, moveHeadline, worthMove } from "@/features/moves/moves";
import { useMoves } from "@/features/moves/useMoves";
import { EffectText } from "@/features/thisweek/TodoList";
import { WaiversContent } from "@/features/waivers/WaiversView";
import { usePageEyebrow } from "@/lib/week";
import Trades, { TradeDetails } from "@/pages/Trades";

const VIEWS = [
  { value: "all", label: "All" },
  { value: "fa", label: "Free agents" },
  { value: "trades", label: "Trades" },
] as const;

const viewOf = (raw: string | null): MoveView => (raw === "fa" || raw === "trades" ? raw : "all");

/**
 * Moves: one ranked list of free agent adds and trade ideas (?view=fa|trades filters it), the live trade
 * builder under it, and the full tables in a closed disclosure.
 */
export default function Moves() {
  const [params, setParams] = useSearchParams();
  const view = viewOf(params.get("view"));
  const eyebrow = usePageEyebrow("Moves");
  const { pending, moves, addsError, tradesFailed } = useMoves();
  const top = moves[0];
  const choose = (next: string) => {
    if (!next) return; // clicking the selected item would clear a single-select group
    setParams((prev) => {
      const out = new URLSearchParams(prev);
      out.set("view", next);
      return out;
    }, { replace: true });
  };
  const title = pending ? "Looking for your best move…" : addsError ? "Moves did not load" : moveHeadline(top);
  const answer = top && worthMove(top) && !pending ? <EffectText todo={top} /> : undefined;
  return (
    <div className="flex flex-col">
      <PageHeader title={title} eyebrow={eyebrow} answer={answer} />
      <section aria-labelledby="moves-heading" className="mb-8 rounded-xl bg-panel p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="moves-heading" className="text-heading font-semibold">Moves, best first</h2>
          <ToggleGroup type="single" aria-label="Moves view" value={view} onValueChange={choose}>
            {VIEWS.map((v) => (
              <ToggleGroupItem key={v.value} value={v.value}>{v.label}</ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        {addsError !== null ? (
          <p role="alert" className="text-body text-warning">The free agent list did not load: {addsError}</p>
        ) : pending ? (
          <p role="status" className="text-muted">Simulating your free agents…</p>
        ) : (
          <MoveList moves={filterMoves(moves, view)} />
        )}
        {tradesFailed && <p role="alert" className="mt-3 text-caption text-warning">Trade ideas did not load, so only free agents are listed.</p>}
        <p className="measure mt-3 text-caption text-muted">
          Ordered by playoff-odds change first, then fantasy points; the two are not converted. Points are net of the drop.
          Trade ideas are your stored finds; build any other trade below.
        </p>
      </section>
      <Trades />
      <details className="mt-8 border-t border-line pt-2">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-heading font-semibold">Details</summary>
        <div className="flex flex-col gap-8 pt-4">
          <WaiversContent />
          <TradeDetails />
        </div>
      </details>
    </div>
  );
}
