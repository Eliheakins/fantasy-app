import { useQueryState } from "@/shared/lib/useQueryState";

import { GranularitySelector } from "@/features/explore/GranularitySelector";
import { MinPlaysSlider } from "@/features/explore/MinPlaysSlider";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/shared/components/ui/accordion";

/**
 * Granularity + min plays in one collapsible block (sidebar height).
 */
export function AggregationSection() {
  const { state } = useQueryState();
  const activeGranularity = state.granularity;
  const minPlays = state.minPlays;

  const summary = `${activeGranularity.replace(/_/g, " ")} · min ${minPlays} plays`;

  return (
    <section className="rounded-xl border border-border bg-input/30 p-4">
      <Accordion type="single" defaultValue="aggregation" collapsible>
        <AccordionItem value="aggregation" className="border-0">
          <AccordionTrigger className="py-2 hover:no-underline">
            <div className="flex flex-col items-start gap-0.5 pr-2 text-left">
              <span className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Aggregation</span>
              <span className="text-xs font-normal normal-case text-ink-muted">{summary}</span>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-5 border-t border-border pt-4">
              <GranularitySelector embedded />
              <MinPlaysSlider embedded />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </section>
  );
}
