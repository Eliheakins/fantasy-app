import { useQueryState } from "@/features/explore/useQueryState";

import { GranularitySelector } from "@/features/explore/GranularitySelector";
import { MinPlaysSlider } from "@/features/explore/MinPlaysSlider";
import { RankingControl } from "@/features/explore/RankingControl";
import { SplitControl } from "@/features/explore/SplitControl";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

/**
 * Granularity, min plays, ranking and split in one collapsible block (sidebar height).
 */
export function AggregationSection() {
  const { state } = useQueryState();
  const activeGranularity = state.granularity;
  const minPlays = state.minPlays;

  const ranking =
    state.order && state.limit !== null
      ? ` · ${state.order.direction === "desc" ? "top" : "bottom"} ${state.limit}`
      : "";
  const split = state.split ? ` · by ${state.split}` : "";
  const summary = `${activeGranularity.replace(/_/g, " ")} · min ${minPlays} plays${ranking}${split}`;

  return (
    <section className="border-b border-border pb-5">
      <Accordion type="single" defaultValue="aggregation" collapsible>
        <AccordionItem value="aggregation" className="border-0">
          <AccordionTrigger className="py-2 hover:no-underline">
            <div className="flex flex-col items-start gap-0.5 pr-2 text-left">
              <span className="text-body font-semibold uppercase tracking-wide text-muted">Aggregation</span>
              <span className="text-caption font-normal normal-case text-muted">{summary}</span>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-5 border-t border-border pt-4">
              <GranularitySelector embedded />
              <MinPlaysSlider embedded />
              <RankingControl />
              <SplitControl />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </section>
  );
}
