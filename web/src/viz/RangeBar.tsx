import { type Domain, layoutRange, type Range, rangeLabel } from "./rangeAxis";

type RangeBarProps = Range & {
  /** Shared axis for the whole table; build it with sharedDomain(rows). */
  domain: Domain;
  width?: number;
  height?: number;
  /** Names the bar for assistive tech: "Opponent: Median 115.0, range 85.0 to 145.0". */
  name?: string;
  /** Neutral tones for comparing two bars: the default is the table look. */
  muted?: boolean;
};

const TICK_WIDTH = 3;
const BAR_HEIGHT_RATIO = 0.5;

/** p10 to p90 bar with a median tick. Median-only rows draw the tick alone. */
export function RangeBar({ domain, width = 120, height = 16, name, muted = false, ...range }: RangeBarProps) {
  const { bar, tick } = layoutRange(range, domain, width);
  const label = name ? `${name}: ${rangeLabel(range)}` : rangeLabel(range);
  const barHeight = height * BAR_HEIGHT_RATIO;
  return (
    <svg
      role="img"
      aria-label={label}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="inline-block align-middle"
    >
      {bar && (
        <rect
          x={bar.x1}
          y={(height - barHeight) / 2}
          width={Math.max(bar.x2 - bar.x1, 1)}
          height={barHeight}
          rx={2}
          className={muted ? "fill-chart-other" : "fill-faint"}
        />
      )}
      {tick !== null && (
        <rect
          x={Math.min(Math.max(tick - TICK_WIDTH / 2, 0), width - TICK_WIDTH)}
          y={1}
          width={TICK_WIDTH}
          height={height - 2}
          className="fill-ink stroke-page"
          strokeWidth={1}
        />
      )}
    </svg>
  );
}
