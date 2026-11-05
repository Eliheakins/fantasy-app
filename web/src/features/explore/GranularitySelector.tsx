import { getStatById } from "@/stat/config/statDictionary";
import { cn } from "@/lib/utils";
import type { GranularityMode } from "@/stat/types/queryBuilder";
import { useQueryState } from "@/features/explore/useQueryState";

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
  const { state, setActiveGranularity: setGranularity } = useQueryState();
  const selectedStatIds = state.stats;
  const activeGranularity = state.granularity;

  const rateLocked = selectedStatIds.some((id) => getStatById(id)?.rate_only);

  const body = (
    <>
      {!embedded ? (
        <h2 className="text-body font-semibold uppercase tracking-wide text-muted">Granularity</h2>
      ) : (
        <h3 className="text-caption font-semibold uppercase tracking-wide text-muted">Granularity</h3>
      )}
      <p className="mt-0.5 text-caption text-muted">
        How the stat is aggregated. Per game divides by the <span className="font-medium text-text">games played</span>{" "}
        (any role) within the season, season type, week and home/away filters. Down, quarter and other situational
        filters do not shrink it.
      </p>
      {rateLocked && (
        <p className="mt-2 text-caption text-warning">
          At least one selected metric is <strong className="font-medium">rate_only</strong> (fixed formula). Total /
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

  return <section className="border-b border-border pb-5">{body}</section>;
}
