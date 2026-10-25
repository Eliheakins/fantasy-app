import { formatPercent } from "@/viz";
import type { ScoreboardSide } from "./logic";
import { winLabel } from "./logic";

const WIDTH = 200;
const HEIGHT = 8;
const MID_TICK = 2;

/** Two-sided bar: the first team's share is the grey length from the left, the second's the rest. */
export function WinSplit({ first, second }: { first: ScoreboardSide; second: ScoreboardSide }) {
  const label = winLabel(first, second);
  if (label === null) return null;
  const share = Math.min(Math.max(first.win_prob ?? 0, 0), 1);
  const lead = (share >= 0.5 ? first : second).roster_id;
  const weight = (side: ScoreboardSide) => (side.roster_id === lead ? "font-semibold" : "text-muted");
  return (
    <div className="flex items-center gap-2 tabular-nums">
      <span className={weight(first)}>{formatPercent(first.win_prob)}</span>
      <svg role="img" aria-label={label} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-2 min-w-0 flex-1" preserveAspectRatio="none">
        <title>{label}</title>
        <rect width={WIDTH} height={HEIGHT} rx={2} className="fill-border" />
        <rect width={share * WIDTH} height={HEIGHT} rx={2} className="fill-range" />
        <rect x={WIDTH / 2 - MID_TICK / 2} width={MID_TICK} height={HEIGHT} className="fill-tick" />
      </svg>
      <span className={weight(second)}>{formatPercent(second.win_prob)}</span>
    </div>
  );
}
