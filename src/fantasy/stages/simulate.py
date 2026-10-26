"""Simulate the rest of each league's season and write playoff and title odds.

Writes sim_season (latest) and appends to sim_season_history (one row per team per run, so the
Outlook chart can show odds over time). Odds assume current rosters: no waiver moves, trades or
injuries beyond the spread already in each player's outcome distribution.

Run: uv run python -m fantasy.stages.simulate
"""

import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from fantasy import stat_line_table, store
from fantasy.config import load_config
from fantasy.sim.availability import kickoffs, remaining_share, scale_projections
from fantasy.sim.environment import Situation, apply_environment
from fantasy.sim.environment import effects_dict as environment_effects
from fantasy.sim.injuries import Flag, InjuryModel, injury_projections, stat_line_blend
from fantasy.sim.lineup import Player
from fantasy.sim.odds import CurrentWeek, LeagueData, build_inputs
from fantasy.sim.outlook import apply_outlook, effects_dict
from fantasy.sim.schedule import pairings, standings
from fantasy.sim.scoring_scale import position_scale, reference_league, scale_points
from fantasy.sim.season import N_PLAYOFF_TEAMS, SeasonInputs, conditional_odds, simulate_season
from fantasy.stages.crosswalk import TEAM_MAP
from fantasy.stages.distributions import calibrated
from fantasy.stages.environment import live as environment_live
from fantasy.stages.injuries import PRACTICE
from fantasy.stages.outlook import live_context
from fantasy.store import SKILL

K_HISTORY_YEARS = 3  # kicker scoring is fit on this many seasons before the current one
MAX_UNMAPPED = 2  # rostered skill players with no nflverse id, per league, before the stage stops
MAX_NO_PROJECTION = 3  # rostered skill players with no projection at all, per league
MIN_CORRELATION_PAIRS = 10  # same-team role pairs a league needs before the fallback is thin
DEF_MEAN, DEF_VAR = 8.0, 25.0  # fallback when too few starting defenses have scored
MIN_DEF_ROWS = 20  # otherwise use the league's own starting-defense scores


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

    def left(row: dict) -> float:
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


# Sleeper projects 0 for these, but the injury layer already applies their chance of playing
SLEEPER_ZEROED_STATUSES = frozenset({"Questionable", "Doubtful"})


def _other_sources(league_id: str, id_map: pl.DataFrame, current: int) -> list[pl.DataFrame]:
    """Each configured source's projections (`blend_sources`; gsis_id, week, other): Sleeper for
    the weeks it projects (the next four), FFToday and prop lines for the current week only. A
    missing table is skipped."""
    others = []
    for source in load_config().blend_sources:
        table = {"sleeper": "proj_sleeper", "props": "proj_props"}.get(source, "proj_outside")
        try:
            theirs = store.read_table(table).filter(pl.col("league_id") == league_id)
        except FileNotFoundError:
            continue
        if source == "sleeper":
            theirs = theirs.join(id_map, on="sleeper_id").drop_nulls("gsis_id")
        else:
            theirs = theirs.filter(pl.col("week") == current)
        if table == "proj_outside":
            theirs = theirs.filter(pl.col("source") == source)
        others.append(theirs.select("gsis_id", "week", other=pl.col("projection")))
    return others


# effects measured in points, so they scale with a league's scoring; the rest are ratios
OUTLOOK_POINT_KINDS = frozenset({"vac_target", "vac_carry"})
ENVIRONMENT_POINT_KINDS = frozenset({"opp_cb_out", "team_pass_epa", "team_sack_rate"})


def _scale_to_league(league_id: str, table: pl.DataFrame | None = None) -> dict[str, float]:
    """Each position's mean projection here over the league the effects were measured in."""
    reference = reference_league(store.read_table("leagues", "raw"))
    projections = store.projection_table() if table is None else table
    history = projections.filter(~pl.col("is_future") & pl.col("has_history"))
    return position_scale(history, league_id, reference)


def _apply_outlook(
    projections: pl.DataFrame, current: int, scale: dict[str, float]
) -> pl.DataFrame:
    """Return ramps and teammate vacancy, when the effects have been measured."""
    try:
        effects = effects_dict(store.read_table("outlook_effects"))
    except FileNotFoundError:
        return projections
    effects = scale_points(effects, scale, OUTLOOK_POINT_KINDS)
    context = live_context(
        store.read_table("nfl_player_stats", "raw"),
        store.read_table("nfl_team_stats", "raw"),
        store.read_table("team_games"),
        store.read_table("nfl_injuries", "raw"),
        load_config().season,
        current,
    )
    return apply_outlook(projections, context, effects, current)


def _apply_environment(
    projections: pl.DataFrame, current: int, model: InjuryModel | None, scale: dict[str, float]
) -> pl.DataFrame:
    """Offense efficiency and opposing-corner effects, when they have been measured and the
    config has the layer on."""
    if not load_config().environment_layer:
        return projections
    try:
        effects = environment_effects(store.read_table("environment_effects"))
        efficiency = store.read_table("nfl_team_efficiency", "raw")
    except FileNotFoundError:
        return projections
    effects = scale_points(effects, scale, ENVIRONMENT_POINT_KINDS)
    team_z, cb_absent, opponent = environment_live(
        efficiency,
        store.read_table("nfl_snaps", "raw"),
        store.read_table("nfl_injuries", "raw"),
        store.read_table("team_games"),
        model,
        load_config().season,
        current,
    )
    return apply_environment(projections, Situation(team_z, cb_absent, opponent), effects, current)


def _stat_line(current: int) -> dict[tuple[str, int], float] | None:
    """(gsis id, week) -> chance of a stat line for this season's games from `current`, when the
    learned projections carry it."""
    table = stat_line_table.stored()
    if table is None:
        return None
    rows = table.filter((pl.col("season") == load_config().season) & (pl.col("week") >= current))
    return {(g, w): q for g, w, q in rows.select("gsis_id", "week", "q").iter_rows()}


def _first_game_chance(current: int) -> dict[str, float]:
    """gsis id -> classifier chance of playing this week's game, when the stage has run."""
    try:
        table = store.read_table("availability")
    except FileNotFoundError:
        warnings.warn(
            "no availability table: first-game chances use the injury curves", stacklevel=2
        )
        return {}
    season = load_config().season
    now = table.filter((pl.col("season") == season) & (pl.col("week") == current))
    if now.is_empty():
        latest = table.filter(pl.col("season") == season)["week"].max()
        warnings.warn(
            f"availability table has no rows for week {current} (latest week: {latest!r}); "
            "run the availability stage. First-game chances use the injury curves",
            stacklevel=2,
        )
    return dict(zip(now["gsis_id"], now["p_play"], strict=True))


def _injury_flags(flagged: pl.DataFrame, current: int) -> dict[str, Flag]:
    """gsis id -> (Sleeper status, body part, practice participation). Body part and practice
    come from the latest nflverse injury report this season; practice counts only once a game
    status has been issued, because the history is of final-day practice."""
    reports = store.read_table("nfl_injuries", "raw").filter(
        pl.col("season") == load_config().season
    )
    latest = (
        reports.filter(pl.col("week") <= current)
        .sort("week")
        .group_by("gsis_id")
        .agg(
            pl.coalesce("report_primary_injury", "practice_primary_injury").last().alias("body"),
            pl.col("report_status").last().alias("issued"),
            pl.col("practice_status").last().alias("practice"),
        )
    )
    detail = {
        r["gsis_id"]: (r["body"], PRACTICE.get(r["practice"]) if r["issued"] else None)
        for r in latest.iter_rows(named=True)
    }
    return {
        g: (s, *detail.get(g, (None, None)))
        for g, s in zip(flagged["gsis_id"], flagged["injury_status"], strict=True)
    }


def _report(problem: str, names: list[str], limit: int, lid: str, strict: bool = True) -> None:
    """Warn about what was dropped for `lid`; stop the stage when more than `limit` were. The
    dashboard passes strict=False: a few unprojected rookies should not blank a league's page."""
    if not names:
        return
    message = f"league {lid}: {len(names)} {problem}: {sorted(names)}"
    if strict and len(names) > limit:
        raise RuntimeError(f"{message} (limit {limit})")
    warnings.warn(message, stacklevel=3)


def _load_rosters(
    lid: str, id_map: pl.DataFrame, players: pl.DataFrame, strict: bool = True
) -> pl.DataFrame:
    """Skill players on this league's rosters with their nflverse id. Players that cannot be
    mapped drop out of every odds calculation, so they are counted and listed."""
    joined = (
        store.read_table("rosters", "raw")
        .filter(pl.col("league_id") == lid)
        .join(id_map, on="sleeper_id", how="left")
        .join(players, on="sleeper_id", how="left")
    )
    skill = joined.filter(pl.col("position").is_in(SKILL))
    _report(
        "rostered skill players with no nflverse id",
        skill.filter(pl.col("gsis_id").is_null())["sleeper_id"]
        .unique(maintain_order=True)
        .to_list(),
        MAX_UNMAPPED,
        lid,
        strict,
    )
    _report(
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


def _check_projected(
    rosters: pl.DataFrame, projections: pl.DataFrame, lid: str, strict: bool = True
) -> None:
    """Rostered players with no projection in any remaining week are left out of their team's
    lineup and replaced by a free agent, which silently weakens the team."""
    projected = set(projections["gsis_id"].to_list())
    missing = [g for g in rosters["gsis_id"].unique(maintain_order=True) if g not in projected]
    _report("rostered skill players with no projection", missing, MAX_NO_PROJECTION, lid, strict)


def _check_standings(base: pl.DataFrame, teams: pl.DataFrame, lid: str) -> None:
    """The recomputed win-loss-tie record should match Sleeper's; a mismatch means phantom ties
    or missing weeks in the matchups table. Points are not compared (Sleeper's differ by a point
    or two in one league, see validate_standings). Skipped when Sleeper's record is not stored."""
    record = ["wins", "losses", "ties"]
    if not set(record) <= set(teams.columns):
        return
    joined = base.join(teams.select("roster_id", *record), on="roster_id", suffix="_sleeper")
    bad = joined.filter(pl.any_horizontal(*(pl.col(c) != pl.col(f"{c}_sleeper") for c in record)))
    if bad.height:
        warnings.warn(
            f"league {lid}: recomputed records differ from Sleeper's for rosters "
            f"{sorted(bad['roster_id'].to_list())}; run validate_standings",
            stacklevel=2,
        )


def _check_league_shape(league: dict[str, Any]) -> None:
    """The season simulation assumes the 6-team playoff in sim/season.py."""
    teams = league.get("playoff_teams")
    if teams is not None and int(teams) != N_PLAYOFF_TEAMS:
        raise ValueError(
            f"league {league['league_id']} has {teams} playoff teams; "
            f"sim/season.py supports {N_PLAYOFF_TEAMS}"
        )


def _kicker_and_defense(
    lid: str, current: int, season: int, players: pl.DataFrame, matchup_players: pl.DataFrame
) -> dict[str, float]:
    """Mean and variance of a kicker's and a starting defense's week."""
    kicker = store.read_table("player_points").filter(
        (pl.col("league_id") == lid)
        & (pl.col("position") == "K")
        & (pl.col("season") >= season - K_HISTORY_YEARS)
    )
    k_points = kicker["points"].to_numpy()
    if k_points.size < 2:
        warnings.warn(
            f"league {lid}: {k_points.size} kicker scores since {season - K_HISTORY_YEARS}; "
            "kickers are valued at 0",
            stacklevel=2,
        )
    def_done = (
        matchup_players.filter(
            (pl.col("league_id") == lid) & (pl.col("week") < current) & pl.col("is_starter")
        )
        .join(players, on="sleeper_id")
        .filter((pl.col("position") == "DEF") & pl.col("points").is_not_null())
    )
    def_points = def_done["points"].to_numpy()
    enough = def_points.size >= MIN_DEF_ROWS
    if not enough:
        warnings.warn(
            f"league {lid}: {def_points.size} starting-defense scores (need {MIN_DEF_ROWS}); "
            f"using the fixed defense mean {DEF_MEAN} and variance {DEF_VAR}",
            stacklevel=2,
        )
    return {
        "k_mean": float(k_points.mean()) if k_points.size else 0.0,
        "k_var": float(k_points.var(ddof=1)) if k_points.size > 1 else 0.0,
        "def_mean": float(def_points.mean()) if enough else DEF_MEAN,
        "def_var": float(def_points.var(ddof=1)) if enough else DEF_VAR,
    }


def _spread_inputs(
    lid: str, marginals: pl.DataFrame
) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """Position spreads and same-team role correlations; warns when the league's tables are thin
    (a missing role pair counts as uncorrelated, a missing size tier as the pooled spread)."""
    cv = dict(
        marginals.filter(pl.col("tier") == -1)
        .select("position", "cv")
        .unique(maintain_order=True)
        .iter_rows()
    )
    same_team = store.read_table("correlation_pairs").filter(
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


def _layered_projections(
    lid: str,
    current: int,
    id_map: pl.DataFrame,
    sleeper_players: pl.DataFrame,
    projection_table: pl.DataFrame,
) -> tuple[pl.DataFrame, dict[str, Flag]]:
    """Future projections after calibration, the source blend and the injury, outlook and
    environment layers, and the injury flags they used."""
    future = projection_table.filter(
        (pl.col("league_id") == lid) & pl.col("is_future") & (pl.col("week") >= current)
    )
    flagged = (
        sleeper_players.select("sleeper_id", "injury_status")
        .filter(pl.col("injury_status").is_not_null())
        .join(id_map, on="sleeper_id")
        .filter(pl.col("gsis_id").is_not_null())
    )
    flags = _injury_flags(flagged, current)
    try:
        model = InjuryModel(store.read_table("injury_effects"))
    except FileNotFoundError:
        model = None
    first_game = _first_game_chance(current) if model is not None else {}
    # our baseline is calibrated by size before it is blended with the other sources; an outside
    # 0 for a Questionable or Doubtful player is dropped like Sleeper's
    zeroed = frozenset(g for g, f in flags.items() if f[0] in SLEEPER_ZEROED_STATUSES)
    blended = stat_line_blend(
        calibrated(future).select("gsis_id", "week", "position", "team", "projection"),
        _other_sources(lid, id_map, current),
        flags,
        model,
        current,
        first_game,
        _stat_line(current),
        zeroed,
    )
    # Sleeper zeroes Out and IR players, which the injury scaling also zeroes; any source's 0 for
    # Questionable and Doubtful players is dropped in the blend, so the scaling applies once
    if model is None:
        projections = scale_projections(blended, {g: f[0] for g, f in flags.items()}, current)
    else:
        projections = injury_projections(blended, flags, model, current, first_game)
    scale = _scale_to_league(lid, projection_table)
    projections = _apply_outlook(projections, current, scale)
    projections = _apply_environment(projections, current, model, scale)
    return projections, flags


def load_league_data(league: dict[str, Any], strict: bool = True) -> LeagueData:
    _check_league_shape(league)
    cfg = load_config()
    lid, current = league["league_id"], int(league["current_week"])
    playoff_start = int(league["playoff_week_start"])
    teams = store.read_table("league_teams", "raw").filter(pl.col("league_id") == lid)
    matchups = store.read_table("matchups", "raw").filter(pl.col("league_id") == lid)
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id")
    sleeper_players = store.read_table("sleeper_players", "raw")
    players = sleeper_players.select("sleeper_id", "position")
    matchup_players = store.read_table("matchup_players", "raw")
    projection_table = store.projection_table()

    base = standings(matchups, current - 1)
    _check_standings(base, teams, lid)
    wins0 = dict(zip(base["roster_id"], base["wins"] + 0.5 * base["ties"], strict=True))
    points0 = dict(zip(base["roster_id"], base["points_for"], strict=True))
    roster_ids = sorted(teams["roster_id"].to_list())

    rosters = _load_rosters(lid, id_map, players, strict)
    projections, flags = _layered_projections(
        lid, current, id_map, sleeper_players, projection_table
    )
    _check_projected(rosters, projections, lid, strict)
    active = (
        sleeper_players.filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position").is_in(SKILL))
        .join(id_map, on="sleeper_id")
        .filter(pl.col("gsis_id_right").is_not_null())
    )
    positions = dict(zip(active["gsis_id_right"], active["position"], strict=True))
    marginals = store.read_table("marginals").filter(pl.col("league_id") == lid)
    cv, rho = _spread_inputs(lid, marginals)
    kd = _kicker_and_defense(lid, current, cfg.season, players, matchup_players)
    mp = (
        matchup_players.filter((pl.col("league_id") == lid) & (pl.col("week") == current))
        .join(players, on="sleeper_id")
        .join(id_map, on="sleeper_id", how="left")
    )
    clock = live_clock(
        mp,
        sleeper_players.select("sleeper_id", "team"),
        store.read_table("nfl_schedules", "raw"),
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
    )


def append_history(latest: pl.DataFrame, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Append this run to the archive table, which is never overwritten, only extended."""
    stamped = latest.with_columns(
        pl.lit(datetime.now(UTC).isoformat(timespec="seconds")).alias("run_at")
    ).select(*store.SCHEMAS["sim_season_history"])
    stamped = store.with_archive("sim_season_history", stamped, data_dir)
    store.write_table("sim_season_history", stamped, "archive", data_dir)
    return stamped


def team_week_rows(data: LeagueData, inp: SeasonInputs) -> list[tuple[Any, ...]]:
    """(league_id, roster_id, week, as_of_week, exp_points, sd_points) for each remaining
    regular-season week. exp_points counts the persistent shift (absence losses sit in it)."""
    expected = inp.mean + inp.shift.mean(axis=2)
    spread = np.sqrt(inp.noise_sd**2 + inp.shift.var(axis=2))
    return [
        (data.league_id, rid, week, data.current_week, float(expected[t, w]), float(spread[t, w]))
        for t, rid in enumerate(data.roster_ids)
        for w, week in enumerate(inp.weeks)
        if week < data.playoff_start
    ]


def run(n_sims: int | None = None, archive: bool = True) -> pl.DataFrame:
    """Simulate every league. `archive=False` skips the append-only history (live ticks)."""
    cfg = load_config()
    n_sims = n_sims or cfg.n_sims
    rows, seed_rows, week_rows, conditional = [], [], [], []
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        data = load_league_data(league)
        inp = build_inputs(data, None, n_sims, 0)
        result = simulate_season(inp)
        week_rows += team_week_rows(data, inp)
        cond = conditional_odds(inp, result).with_columns(
            pl.lit(league["league_id"]).alias("league_id"),
            pl.lit(data.current_week).cast(pl.Int64).alias("as_of_week"),
        )
        conditional.append(cond.select(*store.SCHEMAS["sim_conditional"]))
        for i, roster_id in enumerate(data.roster_ids):
            seed_rows += [
                (league["league_id"], roster_id, k + 1, float(result.p_seed[i, k]))
                for k in range(len(data.roster_ids))
            ]
            rows.append(
                {
                    "league_id": league["league_id"],
                    "team_name": data.team_names[roster_id],
                    "roster_id": roster_id,
                    "as_of_week": data.current_week,
                    "n_sims": n_sims,
                    "p_playoffs": float(result.p_playoffs[i]),
                    "p_bye": float(result.p_bye[i]),
                    "p_title": float(result.p_title[i]),
                    "exp_wins": float(result.exp_wins[i]),
                }
            )
    latest = pl.DataFrame(rows, schema=store.SCHEMAS["sim_season"])
    # one call so the tables cannot drift from sim_season; the append-only history goes last:
    # a failure earlier leaves it behind the tables, never ahead
    store.write_tables(
        {
            "sim_seeds": pl.DataFrame(seed_rows, schema=store.SCHEMAS["sim_seeds"], orient="row"),
            "sim_team_weeks": pl.DataFrame(
                week_rows, schema=store.SCHEMAS["sim_team_weeks"], orient="row"
            ),
            "sim_conditional": pl.concat(conditional)
            if conditional
            else pl.DataFrame(schema=store.SCHEMAS["sim_conditional"]),
            "sim_season": latest,
        }
    )
    if archive:
        append_history(latest)
    return latest


def main() -> None:
    latest = run()
    leagues = store.read_table("leagues", "raw").select("league_id", "league_key")
    pl.Config.set_tbl_rows(30)
    shown = latest.join(leagues, on="league_id").sort(
        ["league_key", "p_title"], descending=[False, True]
    )
    print(shown.select("league_key", "team_name", "p_playoffs", "p_bye", "p_title", "exp_wins"))


if __name__ == "__main__":
    main()
