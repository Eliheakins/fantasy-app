import { getStatById } from "@/config/statDictionary";
import { cn } from "@/lib/utils";
import type { GranularityMode } from "@/types/queryBuilder";
import { useQueryBuilderStore } from "@/store/useQueryBuilderStore";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

const GRANULARITY_ITEMS: { value: GranularityMode; label: string }[] = [
  { value: "total", label: "Total" },
  { value: "per_game", label: "Per game" },
  { value: "per_play", label: "Per play" },
];

export function GranularitySelector() {
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const setGranularity = useQueryBuilderStore((s) => s.setActiveGranularity);

  const rateLocked = selectedStatIds.some((id) => getStatById(id)?.rate_only);

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">Granularity</h2>
      <p className="mt-0.5 text-xs text-zinc-600">
        How the stat is aggregated. Per game divides by <span className="text-zinc-400">active games</span> (any role,
        no situational filters).
      </p>
      {rateLocked && (
        <p className="mt-2 text-xs text-amber-600/90">
          At least one selected metric is <strong className="font-medium">rate_only</strong> (fixed SQL formula). Total /
          Per game are disabled for all columns in this view.
        </p>
      )}
      <ToggleGroup
        type="single"
        value={activeGranularity}
        onValueChange={(v) => {
          if (v) {
            setGranularity(v as GranularityMode);
          }
        }}
        className={cn("mt-3 flex flex-wrap gap-2")}
        aria-label="Result granularity"
      >
        {GRANULARITY_ITEMS.map(({ value, label }) => {
          const disabled = rateLocked && value !== "per_play";
          return (
            <ToggleGroupItem
              key={value}
              value={value}
              disabled={disabled}
              className="min-w-[5.5rem] rounded-md data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40"
            >
              {label}
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>
    </section>
  );
}
