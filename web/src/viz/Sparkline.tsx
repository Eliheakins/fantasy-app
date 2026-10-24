import { formatNumber } from "./format";

type SparklineProps = { values: readonly number[]; width?: number; height?: number };

const PAD = 2;

/** Last-N form line. Needs two points; fewer renders a dash with the same text equivalent. */
export function Sparkline({ values: raw, width = 80, height = 20 }: SparklineProps) {
  const values = raw.filter(Number.isFinite);
  const label = values.length
    ? `Form: ${values.map((v) => formatNumber(v)).join(", ")}`
    : "No recent games";
  if (values.length < 2) {
    return (
      <span role="img" aria-label={label} className="text-mark-muted">
        –
      </span>
    );
  }
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const step = (width - 2 * PAD) / (values.length - 1);
  const points = values
    .map((v, i) => `${PAD + i * step},${height - PAD - ((v - low) / span) * (height - 2 * PAD)}`)
    .join(" ");
  return (
    <svg role="img" aria-label={label} width={width} height={height} className="inline-block align-middle">
      <title>{label}</title>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}
