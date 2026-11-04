import { useMemo, useState } from "react";

import { cn } from "@/shared/lib/utils";

export interface ScatterPoint {
  playerId: string;
  label: string;
  x: number;
  y: number;
}

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) {
    return null;
  }
  if (typeof v === "bigint") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof v === "number") {
    return Number.isFinite(v) ? v : null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function paddedDomain(values: number[]): [number, number] {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) {
    return [0, 1];
  }
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    return [min - pad, max + pad];
  }
  const pad = (max - min) * 0.06;
  return [min - pad, max + pad];
}

const W = 520;
const H = 380;
const M = { top: 28, right: 20, bottom: 44, left: 52 };

interface StatScatterChartProps {
  points: ScatterPoint[];
  xLabel: string;
  yLabel: string;
  className?: string;
}

/**
 * Simple X/Y scatter for comparing two metrics across players (SVG, no chart library).
 */
export function StatScatterChart({ points, xLabel, yLabel, className }: StatScatterChartProps) {
  const [hover, setHover] = useState<number | null>(null);

  const { plotW, plotH, scaleX, scaleY, ticksX, ticksY } = useMemo(() => {
    const plotW = W - M.left - M.right;
    const plotH = H - M.top - M.bottom;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const [x0, x1] = paddedDomain(xs);
    const [y0, y1] = paddedDomain(ys);
    const scaleX = (x: number) => M.left + ((x - x0) / (x1 - x0)) * plotW;
    const scaleY = (y: number) => M.top + plotH - ((y - y0) / (y1 - y0)) * plotH;
    const tickCount = 4;
    const ticksX = Array.from({ length: tickCount + 1 }, (_, i) => x0 + ((x1 - x0) * i) / tickCount);
    const ticksY = Array.from({ length: tickCount + 1 }, (_, i) => y0 + ((y1 - y0) * i) / tickCount);
    return { plotW, plotH, scaleX, scaleY, ticksX, ticksY };
  }, [points]);

  if (points.length === 0) {
    return (
      <div
        className={cn(
          "flex h-[380px] items-center justify-center rounded-md border border-border bg-input/50 text-sm text-ink-muted",
          className,
        )}
      >
        No players with numeric values for both metrics.
      </div>
    );
  }

  const fmt = (n: number) => {
    if (Math.abs(n) >= 1000 || (Math.abs(n) < 0.01 && n !== 0)) {
      return n.toExponential(1);
    }
    return n.toFixed(2);
  };

  return (
    <div className={cn("relative", className)}>
      <svg
        width={W}
        height={H}
        className="max-w-full text-ink-muted"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Scatter of ${yLabel} versus ${xLabel}`}
      >
        <rect x={M.left} y={M.top} width={plotW} height={plotH} fill="#f1f5f9" rx={4} />
        {ticksX.map((t, i) => (
          <g key={`gx-${i}`}>
            <line
              x1={scaleX(t)}
              y1={M.top}
              x2={scaleX(t)}
              y2={M.top + plotH}
              stroke="#e2e8f0"
              strokeDasharray="3 4"
            />
            <text
              x={scaleX(t)}
              y={H - 12}
              textAnchor="middle"
              className="fill-ink-muted text-[9px]"
            >
              {fmt(t)}
            </text>
          </g>
        ))}
        {ticksY.map((t, i) => (
          <g key={`gy-${i}`}>
            <line
              x1={M.left}
              y1={scaleY(t)}
              x2={M.left + plotW}
              y2={scaleY(t)}
              stroke="#e2e8f0"
              strokeDasharray="3 4"
            />
            <text
              x={M.left - 8}
              y={scaleY(t)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-ink-muted text-[9px]"
            >
              {fmt(t)}
            </text>
          </g>
        ))}
        <line
          x1={M.left}
          y1={M.top + plotH}
          x2={M.left + plotW}
          y2={M.top + plotH}
          stroke="#cbd5e1"
        />
        <line x1={M.left} y1={M.top} x2={M.left} y2={M.top + plotH} stroke="#cbd5e1" />
        <text
          x={M.left + plotW / 2}
          y={H - 4}
          textAnchor="middle"
          className="fill-ink text-[11px] font-medium"
        >
          {xLabel}
        </text>
        <text
          x={14}
          y={M.top + plotH / 2}
          textAnchor="middle"
          className="fill-ink text-[11px] font-medium"
          transform={`rotate(-90 14 ${M.top + plotH / 2})`}
        >
          {yLabel}
        </text>
        {points.map((p, i) => {
          const cx = scaleX(p.x);
          const cy = scaleY(p.y);
          const isHover = hover === i;
          return (
            <g key={p.playerId}>
              <circle
                cx={cx}
                cy={cy}
                r={isHover ? 9 : 6}
                className={cn(
                  "cursor-pointer stroke-accent transition-all",
                  isHover ? "fill-accent/45" : "fill-accent/25",
                )}
                strokeWidth={isHover ? 2 : 1}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          );
        })}
      </svg>
      {hover !== null && points[hover] ? (
        <div className="pointer-events-none absolute left-1/2 top-2 z-10 -translate-x-1/2 rounded-md border border-border bg-surface px-3 py-1.5 text-center text-xs shadow-card">
          <div className="font-medium text-ink">{points[hover]!.label}</div>
          <div className="mt-0.5 font-mono text-ink-muted">
            {xLabel}: {points[hover]!.x.toFixed(3)} · {yLabel}: {points[hover]!.y.toFixed(3)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Build scatter points from merged query rows using the two metric column aliases. */
export function buildScatterPoints(
  rows: Record<string, unknown>[],
  xCol: string,
  yCol: string,
  nameByGsis: Map<string, string>,
  /** Which column names the row: player_id, or team_id for team rows. */
  idColumn: "player_id" | "team_id" = "player_id",
): ScatterPoint[] {
  const out: ScatterPoint[] = [];
  for (const row of rows) {
    const pid = String(row[idColumn] ?? "");
    if (!pid) {
      continue;
    }
    const x = toNumber(row[xCol]);
    const y = toNumber(row[yCol]);
    if (x === null || y === null) {
      continue;
    }
    out.push({
      playerId: pid,
      label: nameByGsis.get(pid) ?? pid,
      x,
      y,
    });
  }
  return out;
}
