import { RangeBar, formatNumber } from "@/viz";
import type { Domain } from "@/viz/rangeAxis";
import { cn } from "@/lib/utils";
import { WinSplit } from "./WinSplit";
import {
  type ScoreboardRow,
  type ScoreboardSide,
  cardDomain,
  isMine,
  matchupTitle,
  orderedSides,
  pointsLine,
  rangeText,
  sideName,
} from "./logic";

const RANGE_WIDTH = 120;

function TeamRow({ side, status, domain }: { side: ScoreboardSide; status: ScoreboardRow["status"]; domain: Domain | null }) {
  const final = status === "Final";
  return (
    <div className="py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className={cn("min-w-0 break-words text-body", side.is_me && "font-semibold")}>{sideName(side)}</span>
        <span className="shrink-0 whitespace-nowrap tabular-nums">
          <span className="text-heading font-semibold">{formatNumber(final ? side.points : side.projected)}</span>
          <span className="ml-1 text-caption text-muted" aria-hidden={!final}>{final ? "final" : "proj"}</span>
          <span className="sr-only">{final ? " points" : " projected points"}</span>
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-caption">
        <span className="text-text">{pointsLine(side, status)}</span>
        {!final && domain && (
          <span className="ml-auto inline-flex items-center gap-2 text-muted">
            <RangeBar p10={side.floor} p50={side.median} p90={side.ceiling} domain={domain} width={RANGE_WIDTH} />
            <span className="whitespace-nowrap text-right tabular-nums">{rangeText(side)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/** One matchup: both teams' projected totals and ranges on a shared axis, then the win split. */
export function MatchupCard({ row, showStatus = false }: { row: ScoreboardRow; showStatus?: boolean }) {
  const [first, second] = orderedSides(row);
  const domain = cardDomain(row);
  const mine = isMine(row);
  return (
    <article
      aria-label={matchupTitle(row)}
      className={cn("card", mine && "border-accent")}
    >
      {(mine || showStatus) && (
        <div className="flex items-center justify-between text-caption text-muted">
          <span>{mine ? "Your matchup" : ""}</span>
          {showStatus && <span className="font-medium text-text">{row.status}</span>}
        </div>
      )}
      <div className="divide-y divide-border">
        <TeamRow side={first} status={row.status} domain={domain} />
        <TeamRow side={second} status={row.status} domain={domain} />
      </div>
      <div className="mt-2 text-caption">
        <WinSplit first={first} second={second} />
      </div>
    </article>
  );
}
