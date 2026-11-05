import { Link, useLocation } from "react-router-dom";
import { Callout } from "@/components/Callout";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { useApi } from "@/hooks/useApi";
import { statIdsFor, statLink } from "@/lib/statLink";
import { getStatById } from "@/stat/config/statDictionary";
import { metricSelectAlias } from "@/stat/lib/queryBuilder";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import { useGameLog } from "./useGameLog";

type Props = { gsisId: string; position: string; season: number; onNavigate: () => void };
type PointsRow = { week: number; points: number };

const CELL = "px-2 py-2 text-right tabular-nums";

/** What the sheet shows for one player: header, the season's game log joined with league points by week, and the Explore link. */
export function PlayerSheetBody({ gsisId, position, season, onNavigate }: Props) {
  const { search } = useLocation();
  const statIds = statIdsFor(position) ?? [];
  const log = useGameLog(gsisId, statIds, season);
  const { league, state: ownersState, byPlayer } = useLeagueOwners();
  const points = useApi<PointsRow[]>(
    league === null ? null : `/api/leagues/${encodeURIComponent(league)}/player-points?gsis_id=${encodeURIComponent(gsisId)}&season=${season}`,
  );
  const pointsByWeek = points.kind === "ready" ? new Map(points.data.map((p) => [p.week, p.points])) : null;
  const logByWeek = new Map((log.data?.result.rows ?? []).map((r) => [Number(r.week), r]));
  const weeks = [...new Set([...logByWeek.keys(), ...(pointsByWeek?.keys() ?? [])])].sort((a, b) => a - b);
  const owner = byPlayer?.get(gsisId);
  const href = statLink({ gsisId, position, season, search });
  const waiting = log.isPending || (league !== null && points.kind === "loading");
  return (
    <div className="mt-1 space-y-3">
      <p className="text-body text-muted">
        {[position, log.data?.team, league === null || ownersState.kind !== "ready" ? null : owner ? `Owned by ${owner.owner}` : "Free agent"]
          .filter((part): part is string => Boolean(part))
          .map((part, i) => (
            <span key={part}>
              {i > 0 && <span aria-hidden> · </span>}
              <span>{part}</span>
            </span>
          ))}
      </p>
      {log.isError && <Callout variant="warn">The game log did not load: {log.error.message}</Callout>}
      {league !== null && points.kind === "error" && <Callout variant="warn">League points did not load: {points.error.message}</Callout>}
      {waiting ? (
        <p role="status" className="text-body text-muted">Loading…</p>
      ) : weeks.length === 0 ? (
        log.isError ? null : <p className="text-body text-muted">No games this season.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-body">
            <thead>
              <tr className="border-b border-border text-muted">
                <th scope="col" className={CELL}>Week</th>
                {log.data && statIds.map((id) => <th key={id} scope="col" className={CELL}>{getStatById(id)?.label ?? id}</th>)}
                {pointsByWeek && <th scope="col" className={CELL}>League pts</th>}
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <tr key={week} className="border-b border-border/80 last:border-0">
                  <td className={CELL}>{week}</td>
                  {log.data && statIds.map((id) => <td key={id} className={CELL}>{formatQueryValue(logByWeek.get(week)?.[metricSelectAlias(id)])}</td>)}
                  {pointsByWeek && <td className={CELL}>{formatQueryValue(pointsByWeek.get(week))}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {href && (
        <Link to={href} onClick={onNavigate} className="inline-flex min-h-[44px] items-center underline decoration-border underline-offset-4 hover:decoration-text">
          Open in Explore
        </Link>
      )}
    </div>
  );
}
