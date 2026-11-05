import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useQueryState } from "@/stat/react/useQueryState";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

/**
 * The Context — grouped multi-select chips; each group is collapsible.
 */
export function FilterChipsBar() {
  const { filterChipState: filterState, applyFilterGroup } = useQueryState();
  const groups = useFilterChipGroups();

  return (
    <section className="border-b border-line pb-5">
      <h2 className="text-body font-semibold uppercase tracking-wide text-focus">The Context</h2>
      <p className="mt-0.5 text-caption text-muted">
        Toggle filters for the WHERE clause. Within each row, multiple selections join with{" "}
        <span className="font-medium text-ink">OR</span> (or <span className="font-medium text-ink">AND</span> where
        noted). Rows combine with <span className="font-medium text-ink">AND</span>.
      </p>
      <p className="mt-2 text-caption leading-snug text-muted">
        Some columns (e.g. <code className="rounded bg-panel px-0.5 font-mono text-caption">posteam_type</code>,{" "}
        <code className="rounded bg-panel px-0.5 font-mono text-caption">season_type</code>,{" "}
        <code className="rounded bg-panel px-0.5 font-mono text-caption">xyac_mean_yardage</code>) may need to be added
        to your PBP Parquet pipeline before queries succeed.
      </p>

      <Accordion type="multiple" className="mt-4 w-full">
        {groups.map((group) => {
          const optionIds = group.options.map((o) => o.id);
          const value = optionIds.filter((id) => Boolean(filterState[id]));
          const activeCount = value.length;

          return (
            <AccordionItem key={group.id} value={group.id}>
              <AccordionTrigger className="py-2 text-body hover:no-underline">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-left">
                  <span className="font-medium text-ink">{group.label}</span>
                  {group.description ? (
                    <span className="text-caption font-normal text-muted">({group.description})</span>
                  ) : null}
                  {activeCount > 0 ? (
                    <span className="rounded-full bg-panel px-2 py-0.5 text-caption font-semibold text-focus">
                      {activeCount} on
                    </span>
                  ) : null}
                  <span className="text-caption font-normal text-muted">
                    join <span className="font-medium text-ink">{group.combine.toUpperCase()}</span>
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <ToggleGroup
                  type="multiple"
                  value={value}
                  onValueChange={(next) => applyFilterGroup(optionIds, next)}
                  className="flex flex-wrap justify-start gap-2 pb-2"
                  size="sm"
                  aria-label={group.label}
                >
                  {group.options.map((chip) => (
                    <ToggleGroupItem
                      key={chip.id}
                      value={chip.id}
                      aria-label={chip.label}
                      className="rounded-full data-[state=on]:border-focus/50"
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
