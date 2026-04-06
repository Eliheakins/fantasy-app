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

interface GranularitySelectorProps {
  /** Omit outer card section; use inside another container (e.g. aggregation accordion). */
  embedded?: boolean;
}

export function GranularitySelector({ embedded = false }: GranularitySelectorProps) {
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const setGranularity = useQueryBuilderStore((s) => s.setActiveGranularity);

  const rateLocked = selectedStatIds.some((id) => getStatById(id)?.rate_only);

  const body = (
    <>
      {!embedded ? (
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Granularity</h2>
      ) : (
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Granularity</h3>
      )}
      <p className="mt-0.5 text-xs text-ink-muted">
        How the stat is aggregated. Per game divides by <span className="font-medium text-ink">active games</span> (any
        role, no situational filters).
      </p>
      {rateLocked && (
        <p className="mt-2 text-xs text-warn-fg">
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
    </>
  );

  if (embedded) {
    return <div className="space-y-1">{body}</div>;
  }

  return <section className="rounded-xl border border-border bg-input/30 p-4">{body}</section>;
}
