import { type Domain, layoutRange, type Range, rangeLabel } from "./rangeAxis";

type RangeBarProps = Range & {
  /** Shared axis for the whole table; build it with sharedDomain(rows). */
  domain: Domain;
  width?: number;
  height?: number;
};

const TICK_WIDTH = 3;
const BAR_HEIGHT_RATIO = 0.5;

/** p10 to p90 bar with a median tick. Median-only rows draw the tick alone. */
export function RangeBar({ domain, width = 120, height = 16, ...range }: RangeBarProps) {
  const { bar, tick } = layoutRange(range, domain, width);
  const label = rangeLabel(range);
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
      <title>{label}</title>
      {bar && (
        <rect
          x={bar.x1}
          y={(height - barHeight) / 2}
          width={Math.max(bar.x2 - bar.x1, 1)}
          height={barHeight}
          rx={2}
          className="fill-range"
        />
      )}
      {tick !== null && (
        <rect
          x={Math.min(Math.max(tick - TICK_WIDTH / 2, 0), width - TICK_WIDTH)}
          y={1}
          width={TICK_WIDTH}
          height={height - 2}
          className="fill-tick stroke-page"
          strokeWidth={1}
        />
      )}
    </svg>
  );
}
