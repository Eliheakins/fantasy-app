import { Delta } from "./Delta";
import { type Domain } from "./rangeAxis";
import { scaleLinear } from "d3-scale";
import { formatNumber } from "./format";

type DumbbellProps = {
  before: number;
  after: number;
  domain: Domain;
  /** What the numbers are, for the text equivalent, e.g. "Title odds". */
  measure: string;
  width?: number;
  /** True when the values are percentages: labels get a % sign. */
  percent?: boolean;
};

const HEIGHT = 16;
const RADIUS = 4;

/** Before (hollow) and after (filled) dots joined by a line, with the signed change beside it. */
export function Dumbbell({ before, after, domain, measure, width = 140, percent = false }: DumbbellProps) {
  const x = scaleLinear().domain([...domain]).range([RADIUS + 1, width - RADIUS - 1]).clamp(true);
  const unit = percent ? "%" : "";
  const shown = (v: number) => `${formatNumber(v)}${unit}`;
  if (!Number.isFinite(before) || !Number.isFinite(after)) {
    return <span className="text-mark-muted">{`${measure}: ${shown(before)} before, ${shown(after)} after`}</span>;
  }
  const label = `${measure}: ${shown(before)} before, ${shown(after)} after`;
  return (
    <span className="inline-flex items-center gap-2 align-middle">
      <svg role="img" aria-label={label} width={width} height={HEIGHT} className="shrink-0">
        <title>{label}</title>
        <line x1={x(before)} x2={x(after)} y1={HEIGHT / 2} y2={HEIGHT / 2} className="stroke-range" strokeWidth={2} />
        <circle cx={x(before)} cy={HEIGHT / 2} r={RADIUS} className="fill-page stroke-tick" strokeWidth={1.5} />
        <circle cx={x(after)} cy={HEIGHT / 2} r={RADIUS} className="fill-tick" />
      </svg>
      <Delta points={after - before} />
    </span>
  );
}
