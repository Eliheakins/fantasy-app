import { Link, useLocation } from "react-router-dom";
import { Callout } from "@/components/Callout";
import { useApi } from "@/hooks/useApi";
import { useTeam } from "@/lib/teamContext";
import { statIdsFor, statLink } from "@/lib/statLink";
import { getStatById } from "@/stat/config/statDictionary";
import { metricSelectAlias } from "@/stat/lib/queryBuilder";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import { useGameLog } from "./useGameLog";

type Props = { gsisId: string; position: string; season: number };
type PointsRow = { week: number; points: number };

/** League points to one decimal, whatever their size (formatQueryValue shows three below 1). */
const formatPoints = (v: number | undefined): string => (v === undefined ? "—" : v.toFixed(1));

const CELL = "px-2 py-2 text-right tabular-nums";

/** The player page's body: owner line, the season's game log joined with league points by week, and the Explore link. */
export function PlayerGameLog({ gsisId, position, season }: Props) {
  const { search } = useLocation();
  const statIds = statIdsFor(position) ?? [];
  const log = useGameLog(gsisId, statIds, season);
  const { league } = useTeam();
  const points = useApi<PointsRow[]>(
    league === null ? null : `/api/leagues/${encodeURIComponent(league)}/player-points?gsis_id=${encodeURIComponent(gsisId)}&season=${season}`,
  );
  const pointsByWeek = points.kind === "ready" ? new Map(points.data.map((p) => [p.week, p.points])) : null;
  const logByWeek = new Map((log.data?.rows ?? []).map((r) => [Number(r.week), r]));
  const weeks = [...new Set([...logByWeek.keys(), ...(pointsByWeek?.keys() ?? [])])].sort((a, b) => a - b);
  const href = statLink({ gsisId, position, season, search });
  const waiting = log.isPending || (league !== null && points.kind === "loading");
  return (
    <div className="space-y-3">
      {log.isError && <Callout variant="warn">The game log did not load: {log.error.message}</Callout>}
      {league !== null && points.kind === "error" && <Callout variant="warn">League points did not load: {points.error.message}</Callout>}
      {waiting ? (
        <p role="status" className="text-body text-muted">Loading…</p>
      ) : weeks.length === 0 ? (
        log.isError ? null : <p className="text-body text-muted">No games this season.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full max-w-2xl border-collapse text-body">
            <thead>
              <tr className="border-b border-line text-muted">
                <th scope="col" className={CELL}>Week</th>
                {log.data && statIds.map((id) => <th key={id} scope="col" className={CELL}>{getStatById(id)?.label ?? id}</th>)}
                {pointsByWeek && <th scope="col" className={CELL}>League pts</th>}
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <tr key={week} className="border-b border-line last:border-0">
                  <td className={CELL}>{week}</td>
                  {log.data && statIds.map((id) => <td key={id} className={CELL}>{formatQueryValue(logByWeek.get(week)?.[metricSelectAlias(id)])}</td>)}
                  {pointsByWeek && <td className={CELL}>{formatPoints(pointsByWeek.get(week))}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {href && (
        <Link to={href} className="inline-flex min-h-[44px] items-center underline decoration-border underline-offset-4 hover:decoration-text">
          Open in Find players
        </Link>
      )}
    </div>
  );
}
