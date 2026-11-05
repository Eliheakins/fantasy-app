import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { WaiversContent } from "@/features/waivers/WaiversView";
import { usePageEyebrow } from "@/lib/week";
import Trades from "@/pages/Trades";

const VIEWS = [
  { value: "fa", label: "Free agents" },
  { value: "trades", label: "Trades" },
] as const;
type View = (typeof VIEWS)[number]["value"];

/** Moves: free agents (waivers, streaming) or trades, switched by ?view=fa|trades (default fa). */
export default function Moves() {
  const [params, setParams] = useSearchParams();
  const view: View = params.get("view") === "trades" ? "trades" : "fa";
  const eyebrow = usePageEyebrow("Moves");
  const choose = (next: string) => {
    if (!next) return; // clicking the selected item would clear a single-select group
    setParams((prev) => {
      const out = new URLSearchParams(prev);
      out.set("view", next);
      return out;
    }, { replace: true });
  };
  return (
    <div>
      <PageHeader
        title="Moves"
        eyebrow={eyebrow}
        actions={
          <ToggleGroup type="single" aria-label="Moves view" value={view} onValueChange={choose}>
            {VIEWS.map((v) => (
              <ToggleGroupItem key={v.value} value={v.value}>
                {v.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        }
      />
      {view === "fa" ? <WaiversContent /> : <Trades />}
    </div>
  );
}
