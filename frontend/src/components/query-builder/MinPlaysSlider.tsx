import { useQueryBuilderStore } from "@/store/useQueryBuilderStore";

import { cn } from "@/lib/utils";

export function MinPlaysSlider({ className }: { className?: string }) {
  const minPlays = useQueryBuilderStore((s) => s.minPlays);
  const setMinPlays = useQueryBuilderStore((s) => s.setMinPlays);

  return (
    <section className={cn("rounded-xl border border-zinc-800 bg-zinc-950/80 p-4", className)}>
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">Min plays</h2>
          <p className="mt-0.5 text-xs text-zinc-600">
            HAVING <code className="text-zinc-400">COUNT(*) ≥</code> threshold (0–500). Drops low-volume outliers.
          </p>
        </div>
        <span className="font-mono text-sm tabular-nums text-emerald-400">{minPlays}</span>
      </div>
      <input
        type="range"
        min={0}
        max={500}
        step={1}
        value={minPlays}
        onChange={(e) => setMinPlays(Number(e.target.value))}
        className={cn(
          "mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-800",
          "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-emerald-500",
          "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-emerald-500",
        )}
        aria-label="Minimum plays threshold"
      />
    </section>
  );
}
