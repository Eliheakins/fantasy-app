import {
  STAT_CATEGORY_LABELS,
  STAT_CATEGORY_ORDER,
  getStatById,
  getStatsByCategory,
} from "@/stat/config/statDictionary";
import { describeStat } from "@/stat/lib/queryBuilder";
import { cn } from "@/lib/utils";
import { MAX_SELECTED_STATS } from "@/stat/lib/queryUrl";
import { useQueryState } from "@/features/explore/useQueryState";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

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
            "inline-flex min-h-11 min-w-11 shrink-0 md:min-h-5 md:min-w-5 items-center justify-center rounded-full border border-line",
            "text-caption font-semibold text-muted hover:border-focus/50 hover:text-focus",
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
  const { state, toggleStatId } = useQueryState();
  const selectedIds = state.stats;

  const atCap = selectedIds.length >= MAX_SELECTED_STATS;

  return (
    <TooltipProvider delayDuration={200}>
      <section className={cn("border-b border-line pb-5", className)}>
        <Accordion type="single" defaultValue="what" collapsible>
          <AccordionItem value="what" className="border-0">
            <AccordionTrigger className="py-2 hover:no-underline">
              <div className="flex flex-col items-start gap-0.5 pr-2 text-left">
                <span className="text-body font-semibold uppercase tracking-wide text-focus">The What</span>
                <span className="text-caption font-normal normal-case text-muted">
                  {selectedIds.length}/{MAX_SELECTED_STATS} metrics selected · up to {MAX_SELECTED_STATS} stats
                </span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-3 border-t border-line pt-3">
                <p className="text-caption text-muted">
                  Select up to {MAX_SELECTED_STATS} metrics (same role/play-type bucket are computed in one pass). Hover
                  “?” for definitions.
                </p>

                <div className="flex min-h-0 flex-1 flex-col">
                  <div className="max-h-[min(50vh,24rem)] overflow-y-auto overflow-x-hidden pr-1 lg:max-h-[min(40vh,20rem)]">
                    <Accordion type="multiple" defaultValue={["passing"]} className="w-full">
                      {STAT_CATEGORY_ORDER.map((cat) => {
                        const stats = getStatsByCategory(cat);
                        return (
                          <AccordionItem key={cat} value={cat}>
                            <AccordionTrigger className="text-body">{STAT_CATEGORY_LABELS[cat]}</AccordionTrigger>
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
                                          ? "border-focus/40 bg-panel"
                                          : "border-transparent hover:border-line hover:bg-panel/80",
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
                                          "mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-line bg-surface text-focus",
                                          disableSelect && "cursor-not-allowed",
                                        )}
                                        aria-label={`Select ${s.label}`}
                                      />
                                      <label
                                        htmlFor={`stat-${s.id}`}
                                        className={cn(
                                          "min-h-11 min-w-0 flex-1 cursor-pointer md:min-h-0",
                                          disableSelect && "cursor-not-allowed",
                                        )}
                                      >
                                        <span className="flex items-center gap-2">
                                          <span className="text-body font-medium text-ink">{s.label}</span>
                                          {s.help ? <StatHelpButton label={s.label} help={s.help} /> : null}
                                        </span>
                                        {s.description && !s.help ? (
                                          <span className="mt-0.5 block text-caption text-muted">{s.description}</span>
                                        ) : null}
                                        {s.rate_only ? (
                                          <span className="mt-1 block text-caption text-muted">
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
                  <div className="rounded-md border border-line bg-surface/90 p-2">
                    <p className="text-caption font-medium text-muted">Preview</p>
                    <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto text-caption leading-snug text-muted">
                      {selectedIds.map((id) => {
                        const st = getStatById(id);
                        return st ? (
                          <li key={id} className="border-b border-line pb-1 last:border-0 last:pb-0">
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
