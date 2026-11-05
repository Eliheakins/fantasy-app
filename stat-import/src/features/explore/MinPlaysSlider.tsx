import { useQueryState } from "@/shared/lib/useQueryState";

import { cn } from "@/shared/lib/utils";

interface MinPlaysSliderProps {
  className?: string;
  /** Omit outer card section; use inside another container. */
  embedded?: boolean;
}

export function MinPlaysSlider({ className, embedded = false }: MinPlaysSliderProps) {
  const { state, setMinPlays } = useQueryState();
  const minPlays = state.minPlays;

  const body = (
    <>
      <div className="flex items-center justify-between gap-4">
        <div>
          {!embedded ? (
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Min plays</h2>
          ) : (
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Min plays</h3>
          )}
          <p className="mt-0.5 text-xs text-ink-muted">
            HAVING <code className="rounded bg-surface px-0.5 font-mono text-[11px] text-ink">COUNT(*) ≥</code>{" "}
            threshold (0–500). Drops low-volume outliers.
          </p>
        </div>
        <span className="font-mono text-sm tabular-nums text-accent">{minPlays}</span>
      </div>
      <input
        type="range"
        min={0}
        max={500}
        step={1}
        value={minPlays}
        onChange={(e) => setMinPlays(Number(e.target.value))}
        className={cn(
          "mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-border",
          "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent",
          "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-accent",
        )}
        aria-label="Minimum plays threshold"
      />
    </>
  );

  if (embedded) {
    return <div className={cn("space-y-1", className)}>{body}</div>;
  }

  return <section className={cn("rounded-xl border border-border bg-input/30 p-4", className)}>{body}</section>;
}
