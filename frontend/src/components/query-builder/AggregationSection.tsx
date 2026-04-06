import { useQueryBuilderStore } from "@/store/useQueryBuilderStore";

import { GranularitySelector } from "@/components/query-builder/GranularitySelector";
import { MinPlaysSlider } from "@/components/query-builder/MinPlaysSlider";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

/**
 * Granularity + min plays in one collapsible block (sidebar height).
 */
export function AggregationSection() {
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const minPlays = useQueryBuilderStore((s) => s.minPlays);

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
