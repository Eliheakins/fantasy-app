"""Learned model features: the game table, each player's state after each game, the lines, role and
schedule features, and the design matrix. History and future rows go through the same code, and
every value uses only games strictly before the target game."""

from dataclasses import dataclass, replace

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages import vacancy
from fantasy.stages.lags import lag_asof, latest_asof
from fantasy.stages.project import GROUP
from fantasy.store import week_index

LAG_COLUMNS = (
    "points",
    "exp_pts",
    "tgt",
    "car",
    "att",
    "snap",
    "tshare",
    "rec_td_exp",
    "rush_td_exp",
)
HALF_LIVES = (2, 4, 8)
STATE_FEATURES = [f"{c}_hl{h}" for c in LAG_COLUMNS for h in HALF_LIVES]
STATE_FEATURES += [f"{c}_last" for c in LAG_COLUMNS] + ["n_games", "pts_sd8"]
LINE_FEATURES = ["team_implied", "total_line", "is_home", "spread"]
SCHEDULE_FEATURES = ["rest", "indoor"]
ROLE_COLUMNS = ["age", "years_exp", "draft_pick"]  # static: the latest roster row up to the game
DEPTH_COLUMNS = ["depth_rank"]  # the chart for the game (the origin's chart when further ahead)
ECR_COLUMNS = ["ecr_pos", "ecr_pos_sd", "ecr_pos_range", "ecr_all", "ecr_all_sd", "ecr_all_range"]
PACE_COLUMNS = ["plays", "dropbacks", "pass_oe", "team_epa"]  # lagged team pace
KEY = ["gsis_id", "season", "week"]
ADVANCED_COLUMNS = [c for c in store.SCHEMAS["nfl_advanced"] if c not in KEY]  # lagged
EXTRA_FEATURES = (
    ROLE_COLUMNS
    + DEPTH_COLUMNS
    + ECR_COLUMNS
    + [f"pace_{c}" for c in PACE_COLUMNS]
    + [f"adv_{c}" for c in ADVANCED_COLUMNS]
    + SCHEDULE_FEATURES
    + vacancy.VAC_COLUMNS  # the game's own report; left out where there is none (design)
)
VAC_SET = frozenset(vacancy.VAC_COLUMNS)
FIRST_ACCEPTANCE_SEASON = 2024


def games_frame(
    exp: pl.DataFrame, opp: pl.DataFrame, snaps: pl.DataFrame, stats: pl.DataFrame
) -> pl.DataFrame:
    """Per league and player-game: points, expected points and the usage columns that get lagged."""
    volume = opp.select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        pl.col("rec_attempt").cast(pl.Float64).alias("tgt"),
        pl.col("rush_attempt").cast(pl.Float64).alias("car"),
        pl.col("pass_attempt").cast(pl.Float64).alias("att"),
        pl.col("rec_touchdown_exp").cast(pl.Float64).alias("rec_td_exp"),
        pl.col("rush_touchdown_exp").cast(pl.Float64).alias("rush_td_exp"),
    ).unique(KEY, keep="first", maintain_order=True)
    snap = (
        snaps.filter(pl.col("gsis_id").is_not_null())
        .select(*KEY, pl.col("offense_pct").cast(pl.Float64).alias("snap"))
        .unique(KEY, keep="first", maintain_order=True)
    )
    share = (
        stats.filter(pl.col("season_type") == "REG")
        .select(
            pl.col("player_id").alias("gsis_id"),
            "season",
            "week",
            pl.col("target_share").cast(pl.Float64).alias("tshare"),
        )
        .unique(KEY, keep="first", maintain_order=True)
    )
    return (
        exp.join(volume, on=KEY, how="left")
        .join(snap, on=KEY, how="left")
        .join(share, on=KEY, how="left")
    )


def state_frame(games: pl.DataFrame) -> pl.DataFrame:
    """Each player's state AFTER each game: weighted averages, last values, games played."""
    ordered = games.sort(*GROUP, "season", "week")
    lag: list[pl.Expr] = []
    for column in LAG_COLUMNS:
        # a value missing in the latest game carries the earlier one forward
        lag.extend(
            pl.col(column)
            .forward_fill()
            .ewm_mean(half_life=half_life)
            .over(GROUP)
            .alias(f"{column}_hl{half_life}")
            for half_life in HALF_LIVES
        )
        lag.append(pl.col(column).alias(f"{column}_last"))
    return ordered.with_columns(
        *lag,
        pl.int_range(1, pl.len() + 1).over(GROUP).alias("n_games"),
        pl.col("points").rolling_std(8, min_samples=3).over(GROUP).alias("pts_sd8"),
    ).select(
        *GROUP,
        week_index().alias("t"),
        pl.col("season").alias("as_of_season"),
        pl.col("week").alias("as_of_week"),
        *STATE_FEATURES,
    )


def feature_frame(targets: pl.DataFrame, state: pl.DataFrame, horizon: int = 1) -> pl.DataFrame:
    """targets: league_id, gsis_id, season, week, position, team. Joins the state from the last
    game strictly before the target (a larger horizon looks that many weeks further back)."""
    joined = (
        targets.with_columns((week_index() - (horizon - 1)).alias("t"))
        .sort("t")
        .join_asof(
            state.sort("t"),
            on="t",
            by=GROUP,
            strategy="backward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
    )
    return joined.with_columns(has_history=pl.col("n_games").is_not_null()).drop("t")


def with_lines(frame: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Adds the game's Vegas lines where they exist (later weeks have none)."""
    lines = games.select("season", "week", "team", *LINE_FEATURES).unique(
        ["season", "week", "team"], keep="first", maintain_order=True
    )
    return frame.join(lines, on=["season", "week", "team"], how="left")


@dataclass(frozen=True)
class Extras:
    """Role and context tables from `ingest_role`."""

    roster: pl.DataFrame
    depth: pl.DataFrame
    ecr: pl.DataFrame
    pace: pl.DataFrame
    advanced: pl.DataFrame
    report: pl.DataFrame  # `vacancy.report_table`, with the Sleeper stand-in in `run`
    usage: pl.DataFrame  # `vacancy.usage_table`
    sit_weights: dict[str | None, float]


def load_extras() -> Extras:
    read = {
        n: store.read_table(f"nfl_{n}", "raw")
        for n in ("depth", "ecr", "team_pace", "advanced", "snaps")
    }
    report = vacancy.report_table(store.read_table("nfl_injuries", "raw"))
    usage = vacancy.usage_table(
        store.read_table("nfl_player_stats", "raw"),
        store.read_table("nfl_team_stats", "raw"),
        read["snaps"],
    )
    return Extras(
        roster=store.read_table("nfl_rosters_weekly", "raw"),
        depth=read["depth"],
        ecr=read["ecr"],
        pace=read["team_pace"],
        advanced=read["advanced"],
        report=report,
        usage=usage,
        # fit before the first held-out season, so the held-out check never saw its own rates
        sit_weights=vacancy.sit_weights(report, read["snaps"], FIRST_ACCEPTANCE_SEASON - 1),
    )


def with_sleeper_stand_in(
    extras: Extras, games: pl.DataFrame, season: int, week: int, teams: list[str]
) -> Extras:
    """`extras` for the future rows: the report uses Sleeper's Out players in `week` for the
    teams whose slate (gameday, from `games`) has no final report yet. Prints each team's
    source."""
    players, id_map = store.read_table("sleeper_players", "raw"), store.read_table("id_map")
    stand_in = vacancy.sleeper_report(players, id_map, season, week)
    sources = vacancy.report_sources(extras.report, games, season, week, teams)
    by_source = {s: sorted(t for t, v in sources.items() if v == s) for s in ("final", "sleeper")}
    print(
        f"learn: week {week} vacancy from the final report for {by_source['final']}, "
        f"from Sleeper's Out list for {by_source['sleeper']}"
    )
    unmapped = vacancy.unmapped_out(players, id_map)
    if unmapped:
        print(f"learn: {unmapped} of Sleeper's Out players have no gsis id; left out of vacancy")
    return replace(
        extras, report=vacancy.with_stand_in(extras.report, stand_in, games, season, week)
    )


def with_schedule(frame: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Rest days and an indoor flag for the game: both are known when the schedule is."""
    sched = games.select(
        "season",
        "week",
        "team",
        pl.col("rest").cast(pl.Float64),
        pl.col("roof").is_in(["dome", "closed"]).cast(pl.Float64).alias("indoor"),
    ).unique(["season", "week", "team"], keep="first", maintain_order=True)
    return frame.join(sched, on=["season", "week", "team"], how="left")


def attach_extras(
    frame: pl.DataFrame, extras: Extras, games: pl.DataFrame, horizon: int = 1
) -> pl.DataFrame:
    """Adds the role and context features. One game ahead the depth chart and expert ranking are
    the game's own; further ahead the chart is the origin's and no ranking exists, as for the
    later weeks of a live projection."""
    out = with_schedule(frame, games)
    if horizon == 1:
        out = out.join(
            extras.depth.unique(KEY, keep="first", maintain_order=True), on=KEY, how="left"
        ).join(extras.ecr.unique(KEY, keep="first", maintain_order=True), on=KEY, how="left")
    else:
        out = latest_asof(
            out,
            extras.depth.unique(KEY, keep="first", maintain_order=True),
            "gsis_id",
            DEPTH_COLUMNS,
            horizon - 1,
        )
        out = out.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in ECR_COLUMNS])
    # further ahead the game's report does not exist yet: nobody is listed
    report = extras.report if horizon == 1 else extras.report.clear()
    out = vacancy.vacancy_features(out, report, extras.usage, extras.sit_weights, extras.depth)
    out = latest_asof(
        out, extras.roster.unique(KEY, keep="first", maintain_order=True), "gsis_id", ROLE_COLUMNS
    )
    out = lag_asof(out, extras.pace, "team", PACE_COLUMNS, "pace", horizon - 1)
    return lag_asof(
        out,
        extras.advanced.unique(KEY, keep="first", maintain_order=True),
        "gsis_id",
        ADVANCED_COLUMNS,
        "adv",
        horizon - 1,
    )


def build_features(
    targets: pl.DataFrame,
    state: pl.DataFrame,
    games: pl.DataFrame,
    extras: Extras,
    horizon: int = 1,
) -> pl.DataFrame:
    """State, lines (one game ahead only) and role features for the target rows."""
    features = attach_extras(feature_frame(targets, state, horizon), extras, games, horizon)
    return with_lines(features, games) if horizon == 1 else features


def design(frame: pl.DataFrame, lines: bool, vacancy: bool = True) -> np.ndarray:
    """The feature matrix; without lines or without the vacancy columns for games that have no
    lines or no injury report yet."""
    columns = [*STATE_FEATURES, "week", "is_qb", "is_rb", "is_wr"] + (
        LINE_FEATURES if lines else []
    )
    columns += EXTRA_FEATURES if vacancy else [c for c in EXTRA_FEATURES if c not in VAC_SET]
    out = frame.with_columns(
        *[
            (pl.col("position") == p).cast(pl.Float64).alias(f"is_{p.lower()}")
            for p in ("QB", "RB", "WR")
        ]
    )
    return out.select([pl.col(c).cast(pl.Float64) for c in columns]).to_numpy()
