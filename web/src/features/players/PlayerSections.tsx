import type { ReactNode } from "react";
import type { components } from "@/api/schema";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { Link } from "react-router";
import { ApiBoundary } from "@/components/ApiBoundary";
import { navSearch, type PageUrl } from "@/components/layout/navLinks";
import { Section } from "@/components/Section";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { useTeam } from "@/lib/teamContext";
import type { Domain } from "@/viz/rangeAxis";
import { Delta, Explain, ExplainDelta, formatNumber, formatPercent, RangeBar, sharedDomain, Sparkline } from "@/viz";
import { marketChange, type PlayerProfile, resultSentence, roleKeysFor, roleSeries } from "./profile";
import { useProfile } from "./useProfile";
import { linkButtonClass } from "@/components/ui/styles";

type MarketRow = components["schemas"]["MarketValueRow"];
type HistoryRow = components["schemas"]["MarketHistoryRow"];

const RANGE_WIDTH = 240;
const MIN_HISTORY_POINTS = 4;
const NOT_AVAILABLE = (what: string) => <p className="text-body text-muted">Not available: {what}.</p>;

const nextGameWhy = (p: PlayerProfile) =>
  `The middle of the simulated scores for his week ${p.week} game: half the simulated games land above it and half below. The range below is the 10th to 90th percentile, for a full game.`;
const rosWhy = (p: PlayerProfile) =>
  `His projected points for the rest of the season (${formatNumber(p.ros_points)}) minus those of ${p.replacement_name ?? "the best other free agent"} (${formatNumber(p.replacement_points)}), the replacement at ${p.position}.`;

function NextGame({ p, name, showResult, shared }: { p: PlayerProfile; name?: string; showResult: boolean; shared: Domain | null }) {
  const domain = shared ?? sharedDomain([{ p10: p.p10, p50: p.median, p90: p.p90 }]);
  const result = showResult ? resultSentence(p) : null;
  if (p.median == null || domain === null || p.week == null) {
    return result ? (
      <p className="text-heading font-semibold tabular-nums">{result}</p>
    ) : (
      NOT_AVAILABLE("this player has no projection for the next game")
    );
  }
  return (
    <div className="space-y-2 key-panel">
      {result && <p className="text-body font-semibold tabular-nums">{result}</p>}
      <p className="text-heading font-semibold tabular-nums">
        <Explain why={nextGameWhy(p)}>{formatNumber(p.median)}</Explain> median points, week {p.week}
      </p>
      <RangeBar
        domain={domain}
        width={RANGE_WIDTH}
        p10={p.p10}
        p50={p.median}
        p90={p.p90}
        name={name ? `${name}, next game` : "Next game"}
      />
      {p.next_game && <p className="text-body">{p.next_game}</p>}
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
      <p className="text-heading font-semibold tabular-nums">
        <ExplainDelta points={p.ros_over_replacement} why={rosWhy(p)}>
          {" "}
          points over replacement
        </ExplainDelta>
      </p>
      <p className="text-caption text-muted">
        {formatNumber(p.ros_points)} projected points against {formatNumber(p.replacement_points)} for {p.replacement_name}, the best other
        free agent at {p.position} who is not out.
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

function MarketHistory({ history }: { history: HistoryRow[] }) {
  if (history.length < MIN_HISTORY_POINTS) return null;
  const values = history.map((h) => h.value);
  const label = `Market value, last ${values.length} refreshes, ${Math.round(values[0]!)} to ${Math.round(values[values.length - 1]!)}`;
  return <Sparkline values={values} width={120} height={24} label={label} />;
}

function Market({ rows, history }: { rows: MarketRow[]; history: HistoryRow[] }) {
  const row = rows[0];
  if (!row) return NOT_AVAILABLE("no market value for this player");
  const move = marketChange(row.value, row.trend_30_day);
  return (
    <div className="space-y-1">
      <p className="text-body tabular-nums">
        Value {row.value}
        {row.position_rank != null && `, position rank ${row.position_rank}`}
        {move && (
          <>
            , 30-day change <Delta points={move.change} noise={1} /> ({formatPercent(move.percent)})
          </>
        )}
      </p>
      {row.trend_30_day != null && !move && (
        <p className="text-caption text-muted">
          No 30-day change: the source gives a change as large as the value, so he had no value 30 days ago.
        </p>
      )}
      <MarketHistory history={history} />
      <p className="text-caption text-muted">FantasyCalc value as of today.</p>
    </div>
  );
}

const LINK = linkButtonClass;

/** Where to act on the player: my players go to the Lineup (start or sit) and Trades, others to Trades, free agents to Moves. */
function Owner({ gsisId, here: { search, pathname } }: { gsisId: string; here: PageUrl }) {
  const { league, state, byPlayer } = useLeagueOwners();
  if (league === null || state.kind !== "ready") return null;
  const owner = byPlayer?.get(gsisId);
  const to = (path: string, view?: string) => {
    const params = new URLSearchParams(navSearch(path, search, pathname));
    if (view) params.set("view", view);
    const text = params.toString();
    return { pathname: path, search: text ? `?${text}` : "" };
  };
  return (
    <div className="space-y-1">
      <p className="text-body">{owner ? `Owned by ${owner.owner}` : "Free agent"}</p>
      <p className="flex flex-wrap gap-x-4">
        {owner?.is_mine && (
          <Link to={to("/lineup")} className={LINK}>
            Start or sit on Lineup
          </Link>
        )}
        {owner && (
          <Link to={to("/moves", "trades")} className={LINK}>
            Trade ideas on Moves
          </Link>
        )}
        {!owner && (
          <Link to={to("/moves", "fa")} className={LINK}>
            Add on Moves
          </Link>
        )}
      </p>
    </div>
  );
}

type Level = { level: 2 | 3 };

function Maybe({ show, title, level, children }: { show: boolean; title: string; children: ReactNode } & Level) {
  return show ? (
    <Section title={title} level={level}>
      {children}
    </Section>
  ) : null;
}

/**
 * The player page's sections; the ones with nothing to show are hidden, the key two say not available. At level 2 (the page) the
 * projection sections sit in the left column and role, injury, market and owner in the right; level 3 (Compare) is one column.
 */
export function PlayerSections({
  gsisId,
  level = 2,
  name,
  showResult = true,
  domain = null,
  here,
}: {
  gsisId: string;
  /** The page's URL: the owner links keep its league, team and week. */
  here: PageUrl;
  level?: 2 | 3;
  name?: string;
  /** False where the page header already says the final result. */
  showResult?: boolean;
  /** One range axis shared with the other compared players, so the bars compare by eye. */
  domain?: Domain | null;
}) {
  const profile = useProfile(gsisId);
  const { league } = useTeam();
  const history = useEnvelopeQuery(
    "/api/leagues/{league}/market-history",
    league === null ? null : { path: { league }, query: { id: gsisId } },
  );
  const market = useEnvelopeQuery(
    "/api/leagues/{league}/market-values",
    league === null ? null : { path: { league }, query: { ids: gsisId } },
  );
  return (
    <ApiBoundary state={profile}>
      {(p) => {
        const keys = roleKeysFor(p.position);
        const snap = keys.includes("snap_share") ? roleSeries(p.role_weeks, "snap_share") : [];
        const target = keys.includes("target_share") ? roleSeries(p.role_weeks, "target_share") : [];
        return (
          <div className={level === 2 ? "grid gap-x-8 gap-y-6 lg:grid-cols-2" : "space-y-6"}>
            <div className="min-w-0 space-y-6">
              <Section title="Next game" level={level}>
                <NextGame p={p} name={name} showResult={showResult} shared={domain} />
              </Section>
              <Section title="Rest of season" level={level}>
                <RestOfSeason p={p} />
              </Section>
              <Maybe level={level} show={p.outlook_label != null || !!p.why} title="Why the model expects change">
                <p className="text-body">
                  <span className="font-semibold">{p.outlook_label}</span>
                  {p.why ? `: ${p.why}` : ""}
                </p>
              </Maybe>
            </div>
            <div className="min-w-0 space-y-6">
              <Maybe level={level} show={snap.length + target.length > 0} title="Role">
                <ul className="space-y-1">
                  <RoleLine label="Snap share" values={snap} />
                  <RoleLine label="Target share" values={target} />
                </ul>
                <p className="mt-1 text-caption text-muted">By week this season.</p>
              </Maybe>
              <Maybe level={level} show={!!p.injury_note || p.injury != null || p.chance_to_play != null} title="Injury and chance to play">
                <p className="text-body">
                  {p.injury_note ?? "No injury report."}{" "}
                  {p.chance_to_play != null && `${formatPercent(p.chance_to_play)} to play this game.`}
                </p>
              </Maybe>
              <Section title="Market value" level={level}>
                <ApiBoundary state={market}>
                  {(rows) => <Market rows={rows} history={history.kind === "ready" ? history.data : []} />}
                </ApiBoundary>
              </Section>
              <Section title="Owner" level={level}>
                <Owner gsisId={gsisId} here={here} />
              </Section>
            </div>
          </div>
        );
      }}
    </ApiBoundary>
  );
}
