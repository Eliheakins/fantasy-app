import type { ReactNode } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { Delta, formatNumber, formatPercent, RangeBar, sharedDomain, Sparkline } from "@/viz";
import { type PlayerProfile, roleSeries } from "./profile";
import { useLeaguePath, useProfile } from "./useProfile";

type MarketRow = { gsis_id: string; value: number; overall_rank: number | null; position_rank: number | null; trend_30_day: number | null };

const RANGE_WIDTH = 240;
const NOT_AVAILABLE = (what: string) => <p className="text-body text-muted">Not available: {what}.</p>;

function NextGame({ p }: { p: PlayerProfile }) {
  const domain = sharedDomain([{ p10: p.p10, p50: p.median, p90: p.p90 }]);
  if (p.median == null || domain === null) return NOT_AVAILABLE("this player has no projection for the next game");
  return (
    <div className="space-y-2 rounded-xl border border-panel-line bg-panel px-4 py-3">
      <p className="text-heading font-semibold tabular-nums">{formatNumber(p.median)} median points, week {p.week}</p>
      <RangeBar domain={domain} width={RANGE_WIDTH} p10={p.p10} p50={p.median} p90={p.p90} name="Next game" />
      <p className="text-caption text-muted">
        10th to 90th percentile {formatNumber(p.p10)} to {formatNumber(p.p90)}, for a full game.
        {p.chance_to_play != null && ` Chance to play ${formatPercent(p.chance_to_play)}.`}
      </p>
    </div>
  );
}

function RestOfSeason({ p }: { p: PlayerProfile }) {
  if (p.ros_over_replacement == null || p.ros_points == null) return NOT_AVAILABLE("no projections for the rest of the season");
  return (
    <div className="space-y-1">
      <p className="text-heading font-semibold tabular-nums"><Delta points={p.ros_over_replacement} /> points over replacement</p>
      <p className="text-caption text-muted">
        {formatNumber(p.ros_points)} projected points against {formatNumber(p.replacement_points)} for {p.replacement_name}, the best other free agent at {p.position}.
      </p>
    </div>
  );
}

function RoleLine({ label, values }: { label: string; values: number[] }) {
  if (values.length === 0) return null;
  return (
    <li className="flex items-center gap-3 text-body">
      <span className="w-28">{label}</span>
      <span className="w-12 tabular-nums">{formatNumber(values[values.length - 1], 0)}%</span>
      <Sparkline values={values} width={120} height={24} />
    </li>
  );
}

function Market({ rows }: { rows: MarketRow[] }) {
  const row = rows[0];
  if (!row) return NOT_AVAILABLE("no market value for this player");
  return (
    <div className="space-y-1">
      <p className="text-body tabular-nums">
        Value {row.value}
        {row.position_rank != null && `, position rank ${row.position_rank}`}
        {row.trend_30_day != null && <>, 30-day change <Delta points={row.trend_30_day} noise={1} /></>}
      </p>
      <p className="text-caption text-muted">FantasyCalc, today&apos;s value only: history is not stored, so there is no longer trend.</p>
    </div>
  );
}

function Owner({ gsisId }: { gsisId: string }) {
  const { league, state, byPlayer } = useLeagueOwners();
  if (league === null || state.kind !== "ready") return null;
  const owner = byPlayer?.get(gsisId);
  return <p className="text-body">{owner ? `Owned by ${owner.owner}` : "Free agent"}</p>;
}

function Maybe({ show, title, children }: { show: boolean; title: string; children: ReactNode }) {
  return show ? <Section title={title}>{children}</Section> : null;
}

/** The player page's sections in order; the ones with nothing to show are hidden, the key two say not available. */
export function PlayerSections({ gsisId }: { gsisId: string }) {
  const profile = useProfile(gsisId);
  const market = useLeaguePath<MarketRow[]>(`market-values?ids=${encodeURIComponent(gsisId)}`);
  return (
    <ApiBoundary state={profile}>
      {(p) => {
        const snap = roleSeries(p.role_weeks, "snap_share");
        const target = roleSeries(p.role_weeks, "target_share");
        return (
          <div className="space-y-6">
            <Section title="Next game"><NextGame p={p} /></Section>
            <Section title="Rest of season"><RestOfSeason p={p} /></Section>
            <Maybe show={snap.length + target.length > 0} title="Role">
              <ul className="space-y-1"><RoleLine label="Snap share" values={snap} /><RoleLine label="Target share" values={target} /></ul>
              <p className="mt-1 text-caption text-muted">By week this season.</p>
            </Maybe>
            <Maybe show={p.outlook_label != null || !!p.why} title="Why the model expects change">
              <p className="text-body"><span className="font-semibold">{p.outlook_label}</span>{p.why ? `: ${p.why}` : ""}</p>
            </Maybe>
            <Maybe show={!!p.injury_note || p.injury != null || p.chance_to_play != null} title="Injury and chance to play">
              <p className="text-body">{p.injury_note ?? "No injury report."} {p.chance_to_play != null && `${formatPercent(p.chance_to_play)} to play this game.`}</p>
            </Maybe>
            <Section title="Market value">
              <ApiBoundary state={market}>{(rows) => <Market rows={rows} />}</ApiBoundary>
            </Section>
            <Section title="Owner"><Owner gsisId={gsisId} /></Section>
          </div>
        );
      }}
    </ApiBoundary>
  );
}
