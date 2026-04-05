import {
  STAT_CATEGORY_LABELS,
  STAT_CATEGORY_ORDER,
  getStatById,
  getStatsByCategory,
} from "@/config/statDictionary";
import { describeStat } from "@/lib/queryBuilderSql";
import { cn } from "@/lib/utils";
import { MAX_SELECTED_STATS, useQueryBuilderStore } from "@/store/useQueryBuilderStore";

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
            "inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full border border-zinc-600",
            "text-[10px] font-semibold text-zinc-400 hover:border-emerald-600/60 hover:text-emerald-400",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600",
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
 * The What — multi-select up to MAX_SELECTED_STATS metrics (checkboxes + accordion).
 */
export function StatDictionaryPanel({ className }: StatDictionaryPanelProps) {
  const selectedIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const toggleStatId = useQueryBuilderStore((s) => s.toggleStatId);

  const atCap = selectedIds.length >= MAX_SELECTED_STATS;

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={cn(
          "flex flex-col rounded-xl border border-zinc-800 bg-zinc-950/80 p-4",
          className,
        )}
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">The What</h2>
        <p className="mt-0.5 text-xs text-zinc-600">
          Select up to {MAX_SELECTED_STATS} metrics (same role/play-type bucket can share one SQL query). Hover “?” for
          definitions.
        </p>
        <p className="mt-1 text-[11px] text-zinc-500">
          Selected: {selectedIds.length}/{MAX_SELECTED_STATS}
        </p>

        <div className="mt-3 flex min-h-0 flex-1 flex-col">
          <div className="max-h-[min(70vh,36rem)] overflow-y-auto overflow-x-hidden pr-1">
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
                                  ? "border-emerald-600/50 bg-emerald-950/30"
                                  : "border-transparent hover:border-zinc-800 hover:bg-zinc-900/40",
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
                                  "mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-zinc-600 bg-zinc-900",
                                  "text-emerald-600 focus:ring-emerald-600",
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
                                  <span className="text-sm font-medium text-zinc-100">{s.label}</span>
                                  {s.help ? <StatHelpButton label={s.label} help={s.help} /> : null}
                                </span>
                                {s.description && !s.help ? (
                                  <span className="mt-0.5 block text-xs text-zinc-500">{s.description}</span>
                                ) : null}
                                {s.rate_only ? (
                                  <span className="mt-1 block text-[10px] text-violet-400/90">
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
          <div className="mt-4 rounded-md border border-zinc-800/80 bg-zinc-900/40 p-2">
            <p className="text-[11px] font-medium text-zinc-400">Preview</p>
            <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto text-[10px] leading-snug text-zinc-500">
              {selectedIds.map((id) => {
                const st = getStatById(id);
                return st ? (
                  <li key={id} className="border-b border-zinc-800/60 pb-1 last:border-0 last:pb-0">
                    {describeStat(st)}
                  </li>
                ) : null;
              })}
            </ul>
          </div>
        ) : null}
      </aside>
    </TooltipProvider>
  );
}
