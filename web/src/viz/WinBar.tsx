import { formatPercent } from "./format";

type WinBarProps = { fraction: number | null; width?: number };

const BAR_HEIGHT = 8;

/** Bullet-style 0 to 100 bar in grey with the whole percent beside it. No gauge. */
export function WinBar({ fraction, width = 96 }: WinBarProps) {
  const known = fraction != null && Number.isFinite(fraction);
  const clamped = known ? Math.min(Math.max(fraction, 0), 1) : 0;
  const label = `Win probability ${formatPercent(fraction)}`;
  return (
    <span className="inline-flex items-center gap-2 align-middle">
      <svg role="img" aria-label={label} width={width} height={BAR_HEIGHT} className="shrink-0">
        <title>{label}</title>
        <rect width={width} height={BAR_HEIGHT} rx={2} className="fill-border" />
        <rect width={clamped * width} height={BAR_HEIGHT} rx={2} className="fill-range" />
      </svg>
      <span className="tabular-nums">{formatPercent(fraction)}</span>
    </span>
  );
}
