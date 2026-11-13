import { possessive } from "@/lib/text";
import { Link } from "react-router";

import { ApiBoundary } from "@/components/ApiBoundary";
import { PlayerLink } from "@/components/PlayerLink";
import { Callout } from "@/components/Callout";
import { navSearch, type PageUrl } from "@/components/layout/navLinks";
import { compareHref } from "@/features/players/profile";
import type { LineupRow } from "@/features/lineup/logic";
import { useLeagueApi } from "@/lib/league";
import { Delta, formatNumber, RangeBar, sharedDomain } from "@/viz";

interface Props {
  a: string;
  b: string;
  /** Display names by gsis id, from the question's player matches. */
  names: Readonly<Record<string, string>>;
}

const RANGE_WIDTH = 200;

/** Start/sit for the current week from the lineup route; the choice is the Lineup page's own `recommended` flag. */
export function StartSitAnswer({ a, b, names, here: { pathname, search } }: Props & { here: PageUrl }) {
  const lineup = useLeagueApi("/api/leagues/{league}/lineup");
  const lineupLink = `/lineup${navSearch("/lineup", search, pathname)}`;
  return (
    <section aria-label="Start or sit" className="space-y-3 border-t border-line pt-3">
      <ApiBoundary state={lineup}>{(rows) => <Body rows={rows} a={a} b={b} names={names} />}</ApiBoundary>
      <p className="text-caption text-muted">
        <Link to={compareHref([a, b], search)} className="font-medium text-ink underline-offset-2 hover:underline">
          Compare {names[a] ?? a} and {names[b] ?? b}
        </Link>
        {" · "}
        <Link to={lineupLink} className="font-medium text-ink underline-offset-2 hover:underline">
          Open the Lineup page
        </Link>{" "}
        for the full lineup and win probability.
      </p>
    </section>
  );
}

function Body({ rows, a, b, names }: Props & { rows: LineupRow[] }) {
  const byId = new Map(rows.map((r) => [r.gsis_id, r]));
  const players = [a, b].map((id) => ({ id, name: names[id] ?? id, row: byId.get(id) }));
  const missing = players.filter((p) => !p.row);
  const found = players.flatMap((p) => (p.row ? [{ name: p.name, row: p.row }] : []));
  const locked = found.filter((p) => p.row.locked);

  return (
    <div className="space-y-3">
      <Verdict missing={missing.map((p) => p.name)} locked={locked.map((p) => p.name)} found={found} />
      <Ranges found={found} />
    </div>
  );
}

type Found = { name: string; row: LineupRow };

function Verdict({ missing, locked, found }: { missing: string[]; locked: string[]; found: Found[] }) {
  if (missing.length === 2) {
    return (
      <Callout variant="warn">
        Neither {missing[0]} nor {missing[1]} is on this team&apos;s roster, so there is no lineup projection for them.
      </Callout>
    );
  }
  if (missing.length === 1) {
    return <Callout variant="warn">{missing[0]} is not on this team&apos;s roster, so there is nothing to compare against.</Callout>;
  }
  if (locked.length > 0) {
    return (
      <Callout variant="info">
        {locked.map((n) => `${possessive(n)} game has started`).join(" and ")}, so this week's choice is locked.
      </Callout>
    );
  }
  const [x, y] = found as [Found, Found];
  const starters = found.filter((p) => p.row.recommended);
  if (starters.length === 2) {
    return <p className="text-body font-semibold text-ink">Your lineup starts both</p>;
  }
  if (starters.length === 0) {
    const [more, less] = x.row.projection >= y.row.projection ? [x, y] : [y, x];
    return (
      <div className="space-y-1">
        <p className="text-body font-semibold text-ink">Your lineup benches both</p>
        <p className="text-body text-ink">
          {more.name} projects more ({formatNumber(more.row.projection)} vs {formatNumber(less.row.projection)} projected pts).
        </p>
      </div>
    );
  }
  const [win, lose] = x.row.recommended ? [x, y] : [y, x];
  return (
    <div className="space-y-1">
      <p className="text-body font-semibold text-ink">{`Start ${win.name} over ${lose.name}`}</p>
      <p className="text-body text-ink">
        <Delta points={win.row.projection - lose.row.projection} /> projected pts against starting {lose.name}
      </p>
    </div>
  );
}

function Ranges({ found }: { found: Found[] }) {
  const domain = sharedDomain(found.map((p) => ({ p10: p.row.p10, p50: p.row.projection, p90: p.row.p90 })));
  if (!domain) return null;
  return (
    <ul className="space-y-1">
      {found.map((p) => (
        <li key={p.row.gsis_id} className="flex flex-wrap items-center gap-3 text-body">
          <span className="w-40 text-ink">
            <PlayerLink gsisId={p.row.gsis_id} name={p.name} position={p.row.position} />
          </span>
          <span className="w-12 tabular-nums text-ink">{formatNumber(p.row.projection)}</span>
          <RangeBar domain={domain} width={RANGE_WIDTH} p10={p.row.p10} p50={p.row.projection} p90={p.row.p90} />
        </li>
      ))}
      <li className="text-caption text-muted">Median and 10 to 90% range, in points, this week.</li>
    </ul>
  );
}
