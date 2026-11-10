"""Build a league's `LeagueData` from the stored tables: layered projections, rosters, current
week state and spreads.

The API read path and `stages/simulate.py` both call `load_league_data`; nothing here writes.
"""

import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim.availability import kickoffs, remaining_share
from fantasy.sim.league_checks import (
    check_league_shape,
    check_projected,
    check_standings,
    report,
)
from fantasy.sim.league_projections import (
    kd_slot_projections,
    kicker_and_defense,
    layered_projections,
)
from fantasy.sim.lineup import Player
from fantasy.sim.odds import CurrentWeek, LeagueData
from fantasy.sim.schedule import pairings, standings
from fantasy.store import SKILL
from fantasy.teams import TEAM_MAP

MAX_UNMAPPED = 2  # rostered skill players with no nflverse id, per league, before the stage stops
MIN_CORRELATION_PAIRS = 10  # same-team role pairs a league needs before the fallback is thin


def tier_spreads(marginals: pl.DataFrame) -> dict[str, tuple[tuple[float, float], ...]]:
    """position -> ((upper projection edge, cv), ...) ascending, from the size-tier rows."""
    tiers = (
        marginals.filter(pl.col("tier") >= 0)
        .select("position", "tier", "proj_max", "cv")
        .unique(maintain_order=True)
        .sort("position", "tier")
    )
    out: dict[str, list[tuple[float, float]]] = {}
    for r in tiers.iter_rows(named=True):
        out.setdefault(r["position"], []).append((r["proj_max"], r["cv"]))
    return {position: tuple(rows) for position, rows in out.items()}


def current_state(
    mp: pl.DataFrame,
    projections: dict[str, float],
    week_pool: dict[str, str],
    remaining: dict[str, float] | None = None,
) -> dict[int, CurrentWeek]:
    """Per roster: points already scored by set starters whose game has started, and the
    starters still to score (a game under way counts its remaining share of the projection).

    mp: this week's matchup_players for one league joined to position and gsis_id.
    week_pool maps gsis_id to position for players that have a projection this week.
    remaining maps sleeper_id to the share of that player's game still to play; without it a
    starter counts as started once he has scored.
    """

    def left(row: dict[str, Any]) -> float:
        if remaining is None:
            return 0.0 if (row["points"] or 0) > 0 else 1.0
        return remaining.get(row["sleeper_id"], 1.0)

    out = {}
    for (roster_id,), g in mp.filter(pl.col("is_starter")).group_by("roster_id"):
        rows = [(r, left(r)) for r in g.iter_rows(named=True)]
        started = [r for r, share in rows if share < 1.0]
        players = tuple(
            Player(r["gsis_id"], r["position"], projections[r["gsis_id"]] * share)
            for r, share in rows
            if share > 0
            and r["position"] in SKILL
            and r["gsis_id"] in projections
            and r["gsis_id"] in week_pool
        )
        out[int(roster_id)] = CurrentWeek(
            realized=float(sum(r["points"] or 0.0 for r in started)),
            open_players=players,
            open_k=sum(share for r, share in rows if r["position"] == "K"),
            open_def=sum(share for r, share in rows if r["position"] == "DEF"),
            locked_starters=frozenset(r["gsis_id"] for r in started if r["gsis_id"]),
            kd_actual=float(
                sum(r["points"] or 0.0 for r in started if r["position"] in ("K", "DEF"))
            ),
        )
    return out


def live_clock(
    mp: pl.DataFrame, players: pl.DataFrame, schedules: pl.DataFrame, season: int, week: int
) -> dict[str, float]:
    """Share of each player's game still to play, keyed by sleeper_id (DEF uses the team code)."""
    kicks = kickoffs(schedules, season, week)
    team = dict(zip(players["sleeper_id"], players["team"], strict=True))
    now = datetime.now(UTC)
    out = {}
    for sid in mp["sleeper_id"].unique(maintain_order=True).to_list():
        code: str = team.get(sid) or sid
        out[sid] = remaining_share(kicks.get(TEAM_MAP.get(code, code)), now)
    return out


def _load_rosters(
    lid: str,
    id_map: pl.DataFrame,
    players: pl.DataFrame,
    strict: bool = True,
    *,
    data_dir: Path | None,
) -> pl.DataFrame:
    """Skill players on this league's rosters with their nflverse id. Players that cannot be
    mapped drop out of every odds calculation, so they are counted and listed."""
    joined = (
        store.read_table("rosters", "raw", data_dir)
        .filter(pl.col("league_id") == lid)
        .join(id_map, on="sleeper_id", how="left")
        .join(players, on="sleeper_id", how="left")
    )
    skill = joined.filter(pl.col("position").is_in(SKILL))
    report(
        "rostered skill players with no nflverse id",
        skill.filter(pl.col("gsis_id").is_null())["sleeper_id"]
        .unique(maintain_order=True)
        .to_list(),
        MAX_UNMAPPED,
        lid,
        strict,
    )
    report(
        "rostered players missing from the players file",
        joined.filter(pl.col("position").is_null())["sleeper_id"]
        .unique(maintain_order=True)
        .to_list(),
        MAX_UNMAPPED,
        lid,
        strict,
    )
    return (
        skill.filter(pl.col("gsis_id").is_not_null())
        .select("roster_id", "gsis_id", "position")
        .unique(maintain_order=True)
    )


def _spread_inputs(
    lid: str, marginals: pl.DataFrame, data_dir: Path | None
) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """Position spreads and same-team role correlations; warns when the league's tables are thin
    (a missing role pair counts as uncorrelated, a missing size tier as the pooled spread)."""
    cv = dict(
        marginals.filter(pl.col("tier") == -1)
        .select("position", "cv")
        .unique(maintain_order=True)
        .iter_rows()
    )
    same_team = store.read_table("correlation_pairs", data_dir=data_dir).filter(
        (pl.col("league_id") == lid) & (pl.col("relation") == "same_team")
    )
    rho: dict[tuple[str, str], float] = {}
    for a, b, r in same_team.select("role_a", "role_b", "rho").iter_rows():
        rho[(a, b)] = rho[(b, a)] = r
    tiers = tier_spreads(marginals)
    if same_team.height < MIN_CORRELATION_PAIRS or not set(SKILL) <= set(tiers):
        warnings.warn(
            f"league {lid}: thin spread tables ({same_team.height} same-team role pairs, size "
            f"tiers for {sorted(tiers)}); missing pairs count as uncorrelated, missing tiers "
            "use the pooled spread",
            stacklevel=2,
        )
    return cv, rho


def load_league_data(
    league: dict[str, Any], strict: bool = True, data_dir: Path | None = None
) -> LeagueData:
    """One league's simulation inputs from the stored tables.

    Order: the league shape is checked first (a playoff size the season model cannot fit raises
    before any read), then standings through last week, rosters, the layered projections
    (`league_projections.layered_projections`), spreads, kicker and defense moments, and the
    current week's live state.

    strict=True (the `simulate` stage) raises when more players drop out than a limit allows:
    unmapped or missing rostered players (`MAX_UNMAPPED`) and rostered players with no projection
    (`league_checks.MAX_NO_PROJECTION`). strict=False (the API) only warns, so a few unprojected
    rookies do not blank a league's page. Thin spread tables, a record that differs from Sleeper's
    and too few kicker or defense scores always only warn.
    """
    check_league_shape(league)
    cfg = load_config()
    lid, current = league["league_id"], int(league["current_week"])
    playoff_start = int(league["playoff_week_start"])
    teams = store.read_table("league_teams", "raw", data_dir).filter(pl.col("league_id") == lid)
    matchups = store.read_table("matchups", "raw", data_dir).filter(pl.col("league_id") == lid)
    id_map = store.read_table("id_map", data_dir=data_dir).select("sleeper_id", "gsis_id")
    sleeper_players = store.read_table("sleeper_players", "raw", data_dir)
    players = sleeper_players.select("sleeper_id", "position")
    matchup_players = store.read_table("matchup_players", "raw", data_dir)
    projection_table = store.projection_table(data_dir)

    base = standings(matchups, current - 1)
    check_standings(base, teams, lid)
    wins0 = dict(zip(base["roster_id"], base["wins"] + 0.5 * base["ties"], strict=True))
    points0 = dict(zip(base["roster_id"], base["points_for"], strict=True))
    roster_ids = sorted(teams["roster_id"].to_list())

    rosters = _load_rosters(lid, id_map, players, strict, data_dir=data_dir)
    projections, flags = layered_projections(
        lid, current, id_map, sleeper_players, projection_table, data_dir
    )
    check_projected(rosters, projections, lid, strict)
    active = (
        sleeper_players.filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position").is_in(SKILL))
        .join(id_map, on="sleeper_id")
        .filter(pl.col("gsis_id_right").is_not_null())
    )
    positions = dict(zip(active["gsis_id_right"], active["position"], strict=True))
    marginals = store.read_table("marginals", data_dir=data_dir).filter(pl.col("league_id") == lid)
    cv, rho = _spread_inputs(lid, marginals, data_dir)
    kd = kicker_and_defense(lid, current, cfg.season, players, matchup_players, data_dir)
    mp = (
        matchup_players.filter((pl.col("league_id") == lid) & (pl.col("week") == current))
        .join(players, on="sleeper_id")
        .join(id_map, on="sleeper_id", how="left")
    )
    clock = live_clock(
        mp,
        sleeper_players.select("sleeper_id", "team"),
        store.read_table("nfl_schedules", "raw", data_dir),
        cfg.season,
        current,
    )
    this_week = projections.filter(pl.col("week") == current)
    week_projection = dict(zip(this_week["gsis_id"], this_week["projection"], strict=True))
    week_pool = dict(zip(rosters["gsis_id"], rosters["position"], strict=True))
    week_pool.update(dict.fromkeys(week_projection, ""))

    return LeagueData(
        roster_ids=roster_ids,
        team_names=dict(zip(teams["roster_id"], teams["team_name"], strict=True)),
        current_week=current,
        playoff_start=playoff_start,
        roster_positions=list(league["roster_positions"]),
        rosters=rosters,
        projections=projections,
        cv=cv,
        cv_tiers=tier_spreads(marginals),
        pair_rho=rho,
        pairings={
            week: [(int(a), int(b)) for a, b in g.select("roster_a", "roster_b").iter_rows()]
            for (week,), g in pairings(matchups).group_by("week")
        },
        wins0={int(k): float(v) for k, v in wins0.items()},
        points0={int(k): float(v) for k, v in points0.items()},
        **kd,
        current=current_state(mp, week_projection, week_pool, clock),
        injuries=flags,
        played=frozenset(
            r["gsis_id"]
            for r in mp.iter_rows(named=True)
            if r["gsis_id"] and clock[r["sleeper_id"]] < 1.0
        ),
        live={
            r["gsis_id"]: (float(r["points"] or 0.0), clock[r["sleeper_id"]])
            for r in mp.iter_rows(named=True)
            if r["gsis_id"]
        },
        positions=positions,
        trade_deadline=int(league["trade_deadline"] or 99),
        league_id=lid,
        kd_slot=kd_slot_projections(lid, id_map, current, data_dir),
    )
