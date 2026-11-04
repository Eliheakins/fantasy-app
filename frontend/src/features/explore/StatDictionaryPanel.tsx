import {
  STAT_CATEGORY_LABELS,
  STAT_CATEGORY_ORDER,
  getStatById,
  getStatsByCategory,
} from "@/shared/config/statDictionary";
import { describeStat } from "@/shared/lib/queryBuilder";
import { cn } from "@/shared/lib/utils";
import { MAX_SELECTED_STATS, useQueryBuilderStore } from "@/stores/useQueryBuilderStore";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/shared/components/ui/accordion";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/shared/components/ui/tooltip";

interface StatDictionaryPanelProps {
  className?: string;
}

function StatHelpButton({ label, help }: { label: string; help: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full border border-border",
            "text-[10px] font-semibold text-ink-muted hover:border-accent/50 hover:text-accent",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
          )}
          aria-label={`More about ${label}`}
          onClick={(e) => e.stopPropagation()}
        >
          ?
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" align="start" className="max-w-[18rem]">
        {help}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * The What — multi-select metrics; outer section collapsible, inner accordion per category.
 */
export function StatDictionaryPanel({ className }: StatDictionaryPanelProps) {
  const selectedIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const toggleStatId = useQueryBuilderStore((s) => s.toggleStatId);

  const atCap = selectedIds.length >= MAX_SELECTED_STATS;

  return (
    <TooltipProvider delayDuration={200}>
      <section className={cn("rounded-xl border border-border bg-input/30 p-4", className)}>
        <Accordion type="single" defaultValue="what" collapsible>
          <AccordionItem value="what" className="border-0">
            <AccordionTrigger className="py-2 hover:no-underline">
              <div className="flex flex-col items-start gap-0.5 pr-2 text-left">
                <span className="text-sm font-semibold uppercase tracking-wide text-ink-muted">The What</span>
                <span className="text-xs font-normal normal-case text-ink-muted">
                  {selectedIds.length}/{MAX_SELECTED_STATS} metrics selected · up to {MAX_SELECTED_STATS} stats
                </span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-3 border-t border-border pt-3">
                <p className="text-xs text-ink-muted">
                  Select up to {MAX_SELECTED_STATS} metrics (same role/play-type bucket can share one SQL query). Hover
                  “?” for definitions.
                </p>

                <div className="flex min-h-0 flex-1 flex-col">
                  <div className="max-h-[min(50vh,24rem)] overflow-y-auto overflow-x-hidden pr-1 lg:max-h-[min(40vh,20rem)]">
                    <Accordion type="multiple" defaultValue={["passing"]} className="w-full">
                      {STAT_CATEGORY_ORDER.map((cat) => {
                        const stats = getStatsByCategory(cat);
                        return (
                          <AccordionItem key={cat} value={cat}>
                            <AccordionTrigger className="text-sm">{STAT_CATEGORY_LABELS[cat]}</AccordionTrigger>
                            <AccordionContent>
                              <div className="flex flex-col gap-2 pl-1">
                                {stats.map((s) => {
                                  const checked = selectedIds.includes(s.id);
                                  const disableSelect = !checked && atCap;
                                  return (
                                    <div
                                      key={s.id}
                                      className={cn(
                                        "flex items-start gap-3 rounded-lg border px-3 py-2 transition",
                                        checked
                                          ? "border-accent/40 bg-accent-subtle"
                                          : "border-transparent hover:border-border hover:bg-surface/80",
                                        disableSelect && "opacity-60",
                                      )}
                                    >
                                      <input
                                        type="checkbox"
                                        id={`stat-${s.id}`}
                                        checked={checked}
                                        disabled={disableSelect}
                                        onChange={() => toggleStatId(s.id)}
                                        className={cn(
                                          "mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-border bg-surface text-accent",
                                          "focus:ring-accent focus:ring-offset-0",
                                          disableSelect && "cursor-not-allowed",
                                        )}
                                        aria-label={`Select ${s.label}`}
                                      />
                                      <label
                                        htmlFor={`stat-${s.id}`}
                                        className={cn(
                                          "min-w-0 flex-1 cursor-pointer",
                                          disableSelect && "cursor-not-allowed",
                                        )}
                                      >
                                        <span className="flex items-center gap-2">
                                          <span className="text-sm font-medium text-ink">{s.label}</span>
                                          {s.help ? <StatHelpButton label={s.label} help={s.help} /> : null}
                                        </span>
                                        {s.description && !s.help ? (
                                          <span className="mt-0.5 block text-xs text-ink-muted">{s.description}</span>
                                        ) : null}
                                        {s.rate_only ? (
                                          <span className="mt-1 block text-[10px] text-accent-muted">
                                            rate_only · fixed aggregation
                                            {s.percent_format ? " · header %" : ""}
                                          </span>
                                        ) : null}
                                      </label>
                                    </div>
                                  );
                                })}
                              </div>
                            </AccordionContent>
                          </AccordionItem>
                        );
                      })}
                    </Accordion>
                  </div>
                </div>

                {selectedIds.length > 0 ? (
                  <div className="rounded-md border border-border bg-surface/90 p-2">
                    <p className="text-[11px] font-medium text-ink-muted">Preview</p>
                    <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto text-[10px] leading-snug text-ink-muted">
                      {selectedIds.map((id) => {
                        const st = getStatById(id);
                        return st ? (
                          <li key={id} className="border-b border-border/80 pb-1 last:border-0 last:pb-0">
                            {describeStat(st)}
                          </li>
                        ) : null;
                      })}
                    </ul>
                  </div>
                ) : null}
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </section>
    </TooltipProvider>
  );
}
