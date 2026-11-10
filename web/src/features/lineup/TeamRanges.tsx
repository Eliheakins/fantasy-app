import { RangeBar, formatNumber, sharedDomain } from "@/viz";
import type { WinProbability } from "./logic";

type Option = WinProbability["options"][number];

const BAR_WIDTH = 360;

function Line({
  label,
  p10,
  p50,
  p90,
  domain,
  muted,
}: {
  label: string;
  p10: number;
  p50: number;
  p90: number;
  domain: NonNullable<ReturnType<typeof sharedDomain>>;
  muted?: boolean;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1">
      <span className="w-24 text-body">{label}</span>
      <RangeBar name={label} p10={p10} p50={p50} p90={p90} domain={domain} width={BAR_WIDTH} height={20} muted={muted} />
      <span className="text-caption tabular-nums text-muted">
        {formatNumber(p10, 0)} to {formatNumber(p90, 0)} pts, median {formatNumber(p50, 0)}
      </span>
    </li>
  );
}

/** Both teams' score ranges on one axis, so the overlap is the picture. */
export function TeamRanges({ option }: { option: Option }) {
  const mine = { p10: option.floor, p50: option.median, p90: option.ceiling };
  const theirs = { p10: option.opp_floor, p50: option.opp_median, p90: option.opp_ceiling };
  const domain = sharedDomain([mine, theirs]);
  if (!domain) return null;
  return (
    <ul>
      <Line label="Your team" {...mine} domain={domain} />
      <Line label="Opponent" {...theirs} domain={domain} muted />
    </ul>
  );
}
