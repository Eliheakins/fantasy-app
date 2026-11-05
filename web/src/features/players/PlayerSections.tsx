import type { ReactNode } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { Delta, formatNumber, formatPercent, RangeBar, sharedDomain, Sparkline } from "@/viz";
import { marketChange, type PlayerProfile, resultSentence, roleKeysFor, roleSeries } from "./profile";
import { useLeaguePath, useProfile } from "./useProfile";

type MarketRow = { gsis_id: string; value: number; overall_rank: number | null; position_rank: number | null; trend_30_day: number | null };

const RANGE_WIDTH = 240;
const NOT_AVAILABLE = (what: string) => <p className="text-body text-muted">Not available: {what}.</p>;

function NextGame({ p, name }: { p: PlayerProfile; name?: string }) {
  const domain = sharedDomain([{ p10: p.p10, p50: p.median, p90: p.p90 }]);
  const result = resultSentence(p);
  if (p.median == null || domain === null || p.week == null) {
    return result ? <p className="text-heading font-semibold tabular-nums">{result}</p> : NOT_AVAILABLE("this player has no projection for the next game");
  }
  return (
    <div className="space-y-2 rounded-xl border border-panel-line bg-panel px-4 py-3">
      {result && <p className="text-body font-semibold tabular-nums">{result}</p>}
      <p className="text-heading font-semibold tabular-nums">{formatNumber(p.median)} median points, week {p.week}</p>
      <RangeBar domain={domain} width={RANGE_WIDTH} p10={p.p10} p50={p.median} p90={p.p90} name={name ? `${name}, next game` : "Next game"} />
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
        {formatNumber(p.ros_points)} projected points against {formatNumber(p.replacement_points)} for {p.replacement_name}, the best other free agent at {p.position} who is not out.
        {p.is_out && " He is out, so this is what he is worth if he returns."}
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
      <Sparkline values={values} width={120} height={24} label={`${label} by week, percent`} />
    </li>
  );
}

function Market({ rows }: { rows: MarketRow[] }) {
  const row = rows[0];
  if (!row) return NOT_AVAILABLE("no market value for this player");
  const move = marketChange(row.value, row.trend_30_day);
  return (
    <div className="space-y-1">
      <p className="text-body tabular-nums">
        Value {row.value}
        {row.position_rank != null && `, position rank ${row.position_rank}`}
        {move && <>, 30-day change <Delta points={move.change} noise={1} /> ({formatPercent(move.percent)})</>}
      </p>
      {row.trend_30_day != null && !move && (
        <p className="text-caption text-muted">No 30-day change: the source gives a change as large as the value, so he had no value 30 days ago.</p>
      )}
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

type Level = { level: 2 | 3 };

function Maybe({ show, title, level, children }: { show: boolean; title: string; children: ReactNode } & Level) {
  return show ? <Section title={title} level={level}>{children}</Section> : null;
}

/** The player page's sections in order; the ones with nothing to show are hidden, the key two say not available. */
export function PlayerSections({ gsisId, level = 2, name }: { gsisId: string; level?: 2 | 3; name?: string }) {
  const profile = useProfile(gsisId);
  const market = useLeaguePath<MarketRow[]>(`market-values?ids=${encodeURIComponent(gsisId)}`);
  return (
    <ApiBoundary state={profile}>
      {(p) => {
        const keys = roleKeysFor(p.position);
        const snap = keys.includes("snap_share") ? roleSeries(p.role_weeks, "snap_share") : [];
        const target = keys.includes("target_share") ? roleSeries(p.role_weeks, "target_share") : [];
        return (
          <div className="space-y-6">
            <Section title="Next game" level={level}><NextGame p={p} name={name} /></Section>
            <Section title="Rest of season" level={level}><RestOfSeason p={p} /></Section>
            <Maybe level={level} show={snap.length + target.length > 0} title="Role">
              <ul className="space-y-1"><RoleLine label="Snap share" values={snap} /><RoleLine label="Target share" values={target} /></ul>
              <p className="mt-1 text-caption text-muted">By week this season.</p>
            </Maybe>
            <Maybe level={level} show={p.outlook_label != null || !!p.why} title="Why the model expects change">
              <p className="text-body"><span className="font-semibold">{p.outlook_label}</span>{p.why ? `: ${p.why}` : ""}</p>
            </Maybe>
            <Maybe level={level} show={!!p.injury_note || p.injury != null || p.chance_to_play != null} title="Injury and chance to play">
              <p className="text-body">{p.injury_note ?? "No injury report."} {p.chance_to_play != null && `${formatPercent(p.chance_to_play)} to play this game.`}</p>
            </Maybe>
            <Section title="Market value" level={level}>
              <ApiBoundary state={market}>{(rows) => <Market rows={rows} />}</ApiBoundary>
            </Section>
            <Section title="Owner" level={level}><Owner gsisId={gsisId} /></Section>
          </div>
        );
      }}
    </ApiBoundary>
  );
}
