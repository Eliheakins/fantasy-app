import { FILTER_CHIP_GROUPS } from "@/shared/config/queryBuilderOptions";
import { useQueryBuilderStore } from "@/stores/useQueryBuilderStore";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/shared/components/ui/accordion";
import { ToggleGroup, ToggleGroupItem } from "@/shared/components/ui/toggle-group";

/**
 * The Context — grouped multi-select chips; each group is collapsible.
 */
export function FilterChipsBar() {
  const filterState = useQueryBuilderStore((s) => s.filterChipState);
  const applyFilterGroup = useQueryBuilderStore((s) => s.applyFilterGroup);

  return (
    <section className="rounded-xl border border-border bg-input/30 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">The Context</h2>
      <p className="mt-0.5 text-xs text-ink-muted">
        Toggle filters for the WHERE clause. Within each row, multiple selections join with{" "}
        <span className="font-medium text-ink">OR</span> (or <span className="font-medium text-ink">AND</span> where
        noted). Rows combine with <span className="font-medium text-ink">AND</span>.
      </p>
      <p className="mt-2 text-[11px] leading-snug text-warn-fg">
        Some columns (e.g. <code className="rounded bg-surface px-0.5 font-mono text-[10px]">posteam_type</code>,{" "}
        <code className="rounded bg-surface px-0.5 font-mono text-[10px]">season_type</code>,{" "}
        <code className="rounded bg-surface px-0.5 font-mono text-[10px]">xyac_mean_yardage</code>) may need to be added
        to your PBP Parquet pipeline before queries succeed.
      </p>

      <Accordion type="multiple" className="mt-4 w-full">
        {FILTER_CHIP_GROUPS.map((group) => {
          const optionIds = group.options.map((o) => o.id);
          const value = optionIds.filter((id) => Boolean(filterState[id]));
          const activeCount = value.length;

          return (
            <AccordionItem key={group.id} value={group.id}>
              <AccordionTrigger className="py-2 text-sm hover:no-underline">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-left">
                  <span className="font-medium text-ink">{group.label}</span>
                  {group.description ? (
                    <span className="text-[10px] font-normal text-ink-muted">({group.description})</span>
                  ) : null}
                  {activeCount > 0 ? (
                    <span className="rounded-full bg-accent-subtle px-2 py-0.5 text-[10px] font-semibold text-accent">
                      {activeCount} on
                    </span>
                  ) : null}
                  <span className="text-[10px] font-normal text-ink-muted">
                    join <span className="font-medium text-ink">{group.combine.toUpperCase()}</span>
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <ToggleGroup
                  type="multiple"
                  value={value}
                  onValueChange={(next) => applyFilterGroup(group, next)}
                  className="flex flex-wrap justify-start gap-2 pb-2"
                  size="sm"
                  aria-label={group.label}
                >
                  {group.options.map((chip) => (
                    <ToggleGroupItem
                      key={chip.id}
                      value={chip.id}
                      aria-label={chip.label}
                      className="rounded-full data-[state=on]:border-accent/50"
                    >
                      {chip.label}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </section>
  );
}
