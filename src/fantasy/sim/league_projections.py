"""The projections and kicker and defense inputs of a league's `LeagueData`.

`layered_projections` takes the stored future projections through calibration, the source blend
(`blend_sources`) and the injury and outlook layers. `kicker_and_defense` and `kd_slot_projections`
give the kicker and defense moments and each team's own K and DEF projections by week.
"""

import warnings
from collections.abc import Mapping
from pathlib import Path

import polars as pl

from fantasy import stat_line_table, store
from fantasy.config import load_config
from fantasy.sim.availability import scale_projections
from fantasy.sim.calibration import calibrated
from fantasy.sim.injuries import (
    PRACTICE,
    Flag,
    InjuryModel,
    injury_projections,
    stat_line_blend,
)
from fantasy.sim.outlook import apply_outlook, effects_dict, live_context
from fantasy.sim.scoring_scale import position_scale, reference_league, scale_points
from fantasy.teams import TEAM_MAP

K_HISTORY_YEARS = 3  # kicker scoring is fit on this many seasons before the current one
DEF_MEAN, DEF_VAR = 8.0, 25.0  # fallback when too few starting defenses have scored
MIN_DEF_ROWS = 20  # otherwise use the league's own starting-defense scores

# Sleeper projects 0 for these, but the injury layer already applies their chance of playing
SLEEPER_ZEROED_STATUSES = frozenset({"Questionable", "Doubtful"})
# The only status where the availability classifier beats the injury table on the next game
CLASSIFIER_STATUSES = frozenset({"Questionable"})


def _other_sources(
    league_id: str, id_map: pl.DataFrame, current: int, data_dir: Path | None
) -> dict[str, pl.DataFrame]:
    """Each configured source's projections (`blend_sources`; gsis_id, week, other): Sleeper for
    the weeks it projects (the next four), FFToday and prop lines for the current week only. A
    missing table is skipped."""
    others = {}
    for source in load_config().blend_sources:
        table = {"sleeper": "proj_sleeper", "props": "proj_props"}.get(source, "proj_outside")
        try:
            theirs = store.read_table(table, data_dir=data_dir).filter(
                pl.col("league_id") == league_id
            )
        except FileNotFoundError:
            continue
        if source == "sleeper":
            theirs = theirs.join(id_map, on="sleeper_id").drop_nulls("gsis_id")
        else:
            theirs = theirs.filter(pl.col("week") == current)
        if table == "proj_outside":
            theirs = theirs.filter(pl.col("source") == source)
        others[source] = theirs.select("gsis_id", "week", other=pl.col("projection"))
    return others


# effects measured in points, so they scale with a league's scoring; the rest are ratios
OUTLOOK_POINT_KINDS = frozenset({"vac_target", "vac_carry"})


def _scale_to_league(
    league_id: str, projections: pl.DataFrame, *, data_dir: Path | None
) -> dict[str, float]:
    """Each position's mean projection here over the league the effects were measured in."""
    reference = reference_league(store.read_table("leagues", "raw", data_dir))
    history = projections.filter(~pl.col("is_future") & pl.col("has_history"))
    return position_scale(history, league_id, reference)


def _apply_outlook(
    projections: pl.DataFrame, current: int, scale: dict[str, float], data_dir: Path | None
) -> pl.DataFrame:
    """Return ramps and teammate vacancy, when the effects have been measured."""
    try:
        effects = effects_dict(store.read_table("outlook_effects", data_dir=data_dir))
    except FileNotFoundError:
        return projections
    effects = scale_points(effects, scale, OUTLOOK_POINT_KINDS)
    context = live_context(
        store.read_table("nfl_player_stats", "raw", data_dir),
        store.read_table("nfl_team_stats", "raw", data_dir),
        store.read_table("team_games", data_dir=data_dir),
        store.read_table("nfl_injuries", "raw", data_dir),
        load_config().season,
        current,
    )
    return apply_outlook(projections, context, effects, current)


def stat_line(current: int, data_dir: Path | None) -> dict[tuple[str, int], float] | None:
    """(gsis id, week) -> chance of a stat line for this season's games from `current`, when the
    learned projections carry it."""
    table = stat_line_table.stored(data_dir)
    if table is None:
        return None
    rows = table.filter((pl.col("season") == load_config().season) & (pl.col("week") >= current))
    return {(g, w): q for g, w, q in rows.select("gsis_id", "week", "q").iter_rows()}


def _first_game_chance(
    current: int, flags: Mapping[str, Flag], data_dir: Path | None
) -> dict[str, float]:
    """gsis id -> classifier chance of playing this week's game, for the players it scores better
    than the injury table: Questionable in Sleeper, with a game status on this week's report. The
    classifier learned from final reports, so before one it reads a player Sleeper calls Out as
    healthy; on Out and Doubtful the table is as good (research/availability_midweek_check.py)."""
    try:
        table = store.read_table("availability", data_dir=data_dir)
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
    report = store.read_table("nfl_injuries", "raw", data_dir)
    issued = set(
        report.filter(
            (pl.col("season") == season)
            & (pl.col("week") == current)
            & pl.col("report_status").is_not_null()
        )["gsis_id"]
    )
    return {
        g: p
        for g, p in zip(now["gsis_id"], now["p_play"], strict=True)
        if g in issued and g in flags and flags[g][0] in CLASSIFIER_STATUSES
    }


def _injury_flags(flagged: pl.DataFrame, current: int, data_dir: Path | None) -> dict[str, Flag]:
    """gsis id -> (Sleeper status, body part, practice participation). Body part and practice
    come from the latest nflverse injury report this season; practice counts only once a game
    status has been issued, because the history is of final-day practice."""
    reports = store.read_table("nfl_injuries", "raw", data_dir).filter(
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


def layered_projections(
    lid: str,
    current: int,
    id_map: pl.DataFrame,
    sleeper_players: pl.DataFrame,
    projection_table: pl.DataFrame,
    data_dir: Path | None,
) -> tuple[pl.DataFrame, dict[str, Flag]]:
    """Future projections after calibration, the source blend and the injury and outlook
    layers, and the injury flags they used."""
    future = projection_table.filter(
        (pl.col("league_id") == lid) & pl.col("is_future") & (pl.col("week") >= current)
    )
    flagged = (
        sleeper_players.select("sleeper_id", "injury_status")
        .filter(pl.col("injury_status").is_not_null())
        .join(id_map, on="sleeper_id")
        .filter(pl.col("gsis_id").is_not_null())
    )
    flags = _injury_flags(flagged, current, data_dir)
    try:
        model = InjuryModel(store.read_table("injury_effects", data_dir=data_dir))
    except FileNotFoundError:
        model = None
    first_game = _first_game_chance(current, flags, data_dir) if model is not None else {}
    # our baseline is calibrated by size before it is blended with the other sources; an outside
    # 0 for a Questionable or Doubtful player is dropped like Sleeper's
    zeroed = frozenset(g for g, f in flags.items() if f[0] in SLEEPER_ZEROED_STATUSES)
    blended = stat_line_blend(
        calibrated(future, data_dir).select("gsis_id", "week", "position", "team", "projection"),
        _other_sources(lid, id_map, current, data_dir),
        flags,
        model,
        current,
        first_game,
        stat_line(current, data_dir),
        zeroed,
    )
    # Sleeper zeroes Out and IR players, which the injury scaling also zeroes; any source's 0 for
    # Questionable and Doubtful players is dropped in the blend, so the scaling applies once
    if model is None:
        projections = scale_projections(blended, {g: f[0] for g, f in flags.items()}, current)
    else:
        projections = injury_projections(blended, flags, model, current, first_game)
    scale = _scale_to_league(lid, projection_table, data_dir=data_dir)
    projections = _apply_outlook(projections, current, scale, data_dir)
    return projections, flags


def kicker_and_defense(
    lid: str,
    current: int,
    season: int,
    players: pl.DataFrame,
    matchup_players: pl.DataFrame,
    data_dir: Path | None,
) -> dict[str, float]:
    """Mean and variance of a kicker's and a starting defense's week."""
    kicker = store.read_table("player_points", data_dir=data_dir).filter(
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


def kd_slot_projections(
    lid: str, id_map: pl.DataFrame, current: int, data_dir: Path | None
) -> dict[tuple[str, int, int], float]:
    """Projected points of each team's best rostered K and DEF per week, from `streaming`. A week
    after `current` with no row for a team's units is a bye, worth 0 within the weeks `streaming`
    projects (the current week has no row once a team's game is scored, so it is left out); a team
    with no K or DEF keeps the league mean. Empty without the table."""
    try:
        proj = store.read_table("streaming_projection", "derived", data_dir).filter(
            pl.col("league_id") == lid
        )
    except FileNotFoundError:
        return {}
    rostered = store.read_table("rosters", "raw", data_dir).filter(pl.col("league_id") == lid)
    owned = {
        "DEF": rostered.select(
            "roster_id",
            pl.col("sleeper_id")
            .replace_strict(TEAM_MAP, default=pl.col("sleeper_id"))
            .alias("unit"),
        ),
        "K": rostered.join(id_map.select("sleeper_id", "gsis_id"), on="sleeper_id").select(
            "roster_id", pl.col("gsis_id").alias("unit")
        ),
    }
    out: dict[tuple[str, int, int], float] = {}
    for kind, units in owned.items():
        rows = proj.filter(pl.col("kind") == kind)
        if rows.is_empty():
            continue
        weeks = sorted(rows["week"].unique().to_list())
        best = (
            units.join(rows.select("unit", "week", "projection"), on="unit")
            .group_by("roster_id", "week")
            .agg(pl.col("projection").max())
        )
        have = {(int(r), int(w)): float(v) for r, w, v in best.iter_rows()}
        for roster_id in units.join(rows.select("unit").unique(), on="unit")["roster_id"].unique():
            for week in range(weeks[0], weeks[-1] + 1):
                value = have.get((int(roster_id), week), 0.0 if week > current else None)
                if value is not None:
                    out[(kind, int(roster_id), week)] = value
    return out
