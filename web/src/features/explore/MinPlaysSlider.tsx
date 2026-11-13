import { useQueryState } from "@/stat/react/useQueryState";

import { cn } from "@/lib/utils";
import { eyebrowClass } from "@/components/ui/styles";

/** The min-plays control, inside the query bar's options popover. */
export function MinPlaysSlider() {
  const { state, setMinPlays } = useQueryState();
  const minPlays = state.minPlays;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className={eyebrowClass}>Min plays</h3>
          <p className="mt-0.5 text-caption text-muted">
            Leave out players with fewer plays than this (0 to 500), so one-play outliers do not top a list.
          </p>
        </div>
        <span className="text-body tabular-nums text-focus">{minPlays}</span>
      </div>
      <input
        type="range"
        min={0}
        max={500}
        step={1}
        value={minPlays}
        onChange={(e) => setMinPlays(Number(e.target.value))}
        className={cn(
          "mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-line",
          "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-focus",
          "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-focus",
        )}
        aria-label="Minimum plays threshold"
      />
    </div>
  );
}
