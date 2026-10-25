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

const RANGE_WIDTH = 160;

function TeamRow({ side, status, domain }: { side: ScoreboardSide; status: ScoreboardRow["status"]; domain: Domain | null }) {
  const final = status === "Final";
  return (
    <div className="py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className={cn("min-w-0 break-words text-body", side.is_me && "font-semibold")}>{sideName(side)}</span>
        <span className="shrink-0 text-lg font-semibold tabular-nums">
          {formatNumber(final ? side.points : side.projected)}
          <span className="sr-only">{final ? " points" : " projected points"}</span>
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 text-caption text-muted">
        <span>{pointsLine(side, status)}</span>
        {!final && domain && (
          <span className="inline-flex items-center gap-2">
            <RangeBar p10={side.floor} p50={side.median} p90={side.ceiling} domain={domain} width={RANGE_WIDTH} />
            <span className="tabular-nums">{rangeText(side)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/** One matchup: both teams' projected totals and ranges on a shared axis, then the win split. */
export function MatchupCard({ row }: { row: ScoreboardRow }) {
  const [first, second] = orderedSides(row);
  const domain = cardDomain(row);
  const mine = isMine(row);
  return (
    <article
      aria-label={matchupTitle(row)}
      className={cn("rounded-lg border bg-surface p-[var(--card-pad)]", mine ? "border-accent" : "border-border")}
    >
      <div className="flex items-center justify-between text-caption text-muted">
        <span>{mine ? "Your matchup" : `Matchup ${row.matchup_id ?? ""}`}</span>
        <span className="font-medium text-text">{row.status}</span>
      </div>
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
