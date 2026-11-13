import { Link, useLocation } from "react-router-dom";
import { Callout } from "@/components/Callout";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { useTeam } from "@/lib/teamContext";
import { statIdsFor, statLink } from "@/lib/statLink";
import { getStatById } from "@/stat/config/statDictionary";
import { metricSelectAlias } from "@/stat/lib/queryBuilder";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import { formatNumber } from "@/viz";
import { useGameLog } from "./useGameLog";
import { useProfile } from "./useProfile";

type Props = { gsisId: string; position: string; season: number };

/** League points to one decimal, whatever their size (formatQueryValue shows three below 1). */
const formatPoints = (v: number | undefined): string => (v === undefined ? "—" : formatNumber(v));

const CELL = "px-2 py-2 text-right tabular-nums";

/** The player page's body: owner line, the season's game log joined with league points by week, and the Explore link. */
export function PlayerGameLog({ gsisId, position, season }: Props) {
  const { search } = useLocation();
  const statIds = statIdsFor(position) ?? [];
  const log = useGameLog(gsisId, statIds, season);
  const { league } = useTeam();
  const points = useEnvelopeQuery(
    "/api/leagues/{league}/player-points",
    league === null ? null : { path: { league }, query: { gsis_id: gsisId, season } },
  );
  const pointsByWeek = points.kind === "ready" ? new Map(points.data.map((p) => [p.week, p.points])) : null;
  const logByWeek = new Map((log.data?.rows ?? []).map((r) => [Number(r.week), r]));
  const profile = useProfile(gsisId);
  const byeWeek = profile.kind === "ready" ? profile.data.bye_week : null;
  const snapByWeek = new Map(
    profile.kind === "ready"
      ? profile.data.role_weeks.flatMap((w) => (w.snap_share == null ? [] : [[w.week, w.snap_share * 100] as const]))
      : [],
  );
  const played = [...new Set([...logByWeek.keys(), ...(pointsByWeek?.keys() ?? [])])];
  // every week up to the latest game, so a missed week shows as a bye or a game he sat out
  const weeks = Array.from({ length: Math.max(0, ...played) }, (_, i) => i + 1);
  const href = statLink({ gsisId, position, season, search });
  const columnCount = 1 + (log.data ? statIds.length : 0) + (snapByWeek.size > 0 ? 1 : 0) + (pointsByWeek ? 1 : 0);
  const waiting = log.isPending || (league !== null && points.kind === "loading");
  return (
    <div className="space-y-3">
      {log.isError && <Callout variant="warn">The game log did not load: {log.error.message}</Callout>}
      {league !== null && points.kind === "error" && <Callout variant="warn">League points did not load: {points.error.message}</Callout>}
      {waiting ? (
        <p role="status" className="text-body text-muted">
          Loading…
        </p>
      ) : weeks.length === 0 ? (
        log.isError ? null : (
          <p className="text-body text-muted">No games this season.</p>
        )
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full max-w-2xl border-collapse text-body">
            <thead>
              <tr className="border-b border-line text-muted">
                <th scope="col" className={CELL}>
                  Week
                </th>
                {log.data &&
                  statIds.map((id) => (
                    <th key={id} scope="col" className={CELL}>
                      {getStatById(id)?.label ?? id}
                    </th>
                  ))}
                {snapByWeek.size > 0 && (
                  <th scope="col" className={CELL}>
                    Snap %
                  </th>
                )}
                {pointsByWeek && (
                  <th scope="col" className={CELL}>
                    League pts
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) =>
                played.includes(week) ? (
                  <tr key={week} className="border-b border-line last:border-0">
                    <td className={CELL}>{week}</td>
                    {log.data &&
                      statIds.map((id) => (
                        <td key={id} className={CELL}>
                          {formatQueryValue(logByWeek.get(week)?.[metricSelectAlias(id)])}
                        </td>
                      ))}
                    {snapByWeek.size > 0 && <td className={CELL}>{snapByWeek.has(week) ? formatNumber(snapByWeek.get(week), 0) : "—"}</td>}
                    {pointsByWeek && <td className={CELL}>{formatPoints(pointsByWeek.get(week))}</td>}
                  </tr>
                ) : (
                  <tr key={week} className="border-b border-line text-muted last:border-0">
                    <td className={CELL}>{week}</td>
                    <td className="px-2 py-2 text-left" colSpan={columnCount - 1}>
                      {week === byeWeek ? "Bye" : "Did not play"}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
      {href && (
        <Link to={href} className="inline-flex min-h-[44px] items-center underline decoration-line underline-offset-4 hover:decoration-ink">
          Open in Find players
        </Link>
      )}
    </div>
  );
}
