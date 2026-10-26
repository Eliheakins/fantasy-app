"""Model scorecard: our archived pre-kickoff projections against what happened (see data_api).

For each player-game the last snapshot fetched before that team's kickoff is used, never a later
one. Only games with actual points are scored. Errors use the backtest's definitions (the mean is
floored at `MIN_MEAN`; size tiers are projection thirds with edges from the training seasons), so
the numbers are comparable with `stages/backtest.py`.
"""

import json
import warnings
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.sim.availability import kickoffs
from fantasy.stages.backtest import ALL_TIERS, MIN_MEAN, TRAIN_END, size_tiers
from fantasy.stages.sleeper_projections import score_stats

MODELS = ("learned", "baseline", "sleeper")
ALL = "ALL"
KEY = ["league_id", "gsis_id", "season", "week"]
UTC_TIME = pl.Datetime("us", "UTC")
LONG_SCHEMA = {
    "week": pl.Int64, "position": pl.String, "tier": pl.Int64, "model": pl.String, "err": pl.Float64
}  # fmt: skip


@dataclass(frozen=True)
class Scorecard:
    rows: pl.DataFrame
    excluded: dict[str, int]
    weeks_archived: list[int]
    weeks_scored: list[int]
    has_quantiles: bool  # the snapshots carry only means, so there is no interval coverage
    sleeper_first_fetch: str | None


def _at(column: str = "fetched_at") -> pl.Expr:
    return pl.col(column).str.to_datetime(time_zone="UTC", time_unit="us")


def _last_before_kickoff(snaps: pl.DataFrame, kick: pl.DataFrame) -> pl.DataFrame:
    """Per player-game the latest snapshot fetched before kickoff (`kick` has KEY and kickoff)."""
    return (
        snaps.with_columns(_at().alias("_at"))
        .join(kick, on=KEY)
        .filter(pl.col("_at") < pl.col("kickoff"))
        .sort("_at")
        .unique(KEY, keep="last")
        .drop("_at", "kickoff", strict=False)
    )


def score_games(
    games: pl.DataFrame,
    snaps: pl.DataFrame,
    sleeper: pl.DataFrame | None,
    actuals: pl.DataFrame,
    kick: pl.DataFrame,
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Scored player-games and a count of each reason one was left out.

    games: KEY + team + position. snaps: KEY + fetched_at + learned + baseline. sleeper: the same
    with a `sleeper` column, or None. actuals: KEY + points. kick: season, week, team,
    kickoff (UTC).
    A game is left out as not_final (no actual points), no_kickoff (the team has no kickoff time)
    or no_snapshot (nothing fetched before kickoff), in that order."""
    base = (
        games.join(actuals, on=KEY, how="left")
        .join(kick, on=["season", "week", "team"], how="left")
        .with_columns(
            pl.when(pl.col("points").is_null())
            .then(pl.lit("not_final"))
            .when(pl.col("kickoff").is_null())
            .then(pl.lit("no_kickoff"))
            .alias("_why")
        )
    )
    window = base.filter(pl.col("_why").is_null()).select(*KEY, "kickoff")
    picked = _last_before_kickoff(snaps, window).select(*KEY, "learned", "baseline")
    scored = (
        base.filter(pl.col("_why").is_null())
        .join(picked, on=KEY, how="left")
        .with_columns((pl.col("baseline").is_null() & pl.col("learned").is_null()).alias("_none"))
    )
    has_sleeper = sleeper is not None and not sleeper.is_empty()
    if sleeper is not None and has_sleeper:
        clean = _last_before_kickoff(sleeper, window).select(*KEY, "sleeper")
        scored = scored.join(clean, on=KEY, how="left")
    else:
        scored = scored.with_columns(pl.lit(None, pl.Float64).alias("sleeper"))
    kept = scored.filter(~pl.col("_none"))
    why = base["_why"].value_counts()
    counts = {r["_why"]: r["count"] for r in why.drop_nulls().iter_rows(named=True)}
    out = {
        "games": games.height,
        "scored": kept.height,
        "not_final": counts.get("not_final", 0),
        "no_kickoff": counts.get("no_kickoff", 0),
        "no_snapshot": scored.height - kept.height,
        "sleeper_missing": int(kept["sleeper"].is_null().sum()) if has_sleeper else 0,
    }
    return (
        kept.select(*KEY, "team", "position", pl.col("points").alias("actual"), *MODELS),
        out,
    )


def add_tiers(frame: pl.DataFrame, train: pl.DataFrame) -> pl.DataFrame:
    """A `tier` column (the baseline projection's third, as in the backtest), null for a league and
    position with no training rows. train: league_id, position, projection."""
    parts = []
    for (league_id, position), g in frame.group_by("league_id", "position", maintain_order=True):
        rows = train.filter((pl.col("league_id") == league_id) & (pl.col("position") == position))
        tier = (
            pl.Series("tier", size_tiers(rows["projection"].to_numpy(), g["baseline"].to_numpy()))
            if rows.height and g["baseline"].is_not_null().all()
            else pl.Series("tier", [None] * g.height, dtype=pl.Int64)
        )
        parts.append(g.with_columns(tier.cast(pl.Int64)))
    return pl.concat(parts) if parts else frame.with_columns(pl.lit(None, pl.Int64).alias("tier"))


def error_table(scored: pl.DataFrame) -> pl.DataFrame:
    """Error by week, position, tier and model, each also across all weeks (week null), all
    positions (ALL) and all tiers (-1). scored: week, position, tier, actual, plus a projection
    column per model (a missing column or a null skips that model for that game)."""
    id_cols = [
        pl.col("week").cast(pl.Int64),
        pl.col("position").cast(pl.String),
        pl.col("tier").cast(pl.Int64),
    ]
    frames = [
        scored.select(
            *id_cols,
            pl.lit(m).alias("model"),
            (pl.col(m).cast(pl.Float64).clip(lower_bound=MIN_MEAN) - pl.col("actual")).alias("err"),
        ).drop_nulls("err")
        for m in MODELS
        if m in scored.columns
    ]
    long = pl.concat(frames) if frames else pl.DataFrame(schema=LONG_SCHEMA)
    parts = []
    for by_week, by_pos, by_tier in product((True, False), repeat=3):
        g = long if by_tier else long.with_columns(pl.lit(ALL_TIERS).cast(pl.Int64).alias("tier"))
        g = g.drop_nulls("tier") if by_tier else g
        g = g.with_columns(
            pl.col("week") if by_week else pl.lit(None, pl.Int64).alias("week"),
            pl.col("position") if by_pos else pl.lit(ALL).alias("position"),
        )
        parts.append(
            g.group_by("week", "position", "tier", "model").agg(
                pl.len().cast(pl.Int64).alias("n"),
                pl.col("err").abs().mean().alias("mae"),
                (pl.col("err") ** 2).mean().sqrt().alias("rmse"),
                pl.col("err").mean().alias("bias"),
            )
        )
    schema = ENGINE_SCHEMAS["scorecard"]
    return (
        pl.concat(parts)
        .select(list(schema))
        .cast(schema)  # type: ignore[arg-type]
        .sort("week", "position", "tier", "model", nulls_last=True)
    )


def _kickoff_frame(games: pl.DataFrame, schedules: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for season, week in games.select("season", "week").unique().iter_rows():
        with warnings.catch_warnings():  # teams with no kickoff time are counted, not warned about
            warnings.simplefilter("ignore")
            by_team = kickoffs(schedules, season, week)
        rows += [
            {"season": season, "week": week, "team": t, "kickoff": k.astimezone(None)}
            for t, k in by_team.items()
        ]
    return pl.DataFrame(
        rows,
        schema={"season": pl.Int64, "week": pl.Int64, "team": pl.String, "kickoff": UTC_TIME},
    )


def _sleeper_points(
    snaps: pl.DataFrame, league: dict, id_map: pl.DataFrame, games: pl.DataFrame
) -> pl.DataFrame:
    """Sleeper's projection for the games we track, scored under the league's rules."""
    scoring = json.loads(league["scoring_settings"])
    wanted = snaps.filter(pl.col("week").is_in(games["week"].unique().to_list())).join(
        id_map, on="sleeper_id"
    )
    points = [score_stats(json.loads(s), scoring) for s in wanted["stats"]]
    return wanted.select(
        pl.lit(league["league_id"]).alias("league_id"),
        "gsis_id",
        pl.lit(int(league["season"])).alias("season"),
        "week",
        "fetched_at",
        pl.Series("sleeper", points, dtype=pl.Float64),
    )


def scorecard_of(league_id: str, data_dir: Path = store.DATA_DIR) -> Scorecard:
    """Score a league's archived projections that are final. Empty before the first final game."""
    try:
        snaps = store.read_table("proj_snapshots", "archive", data_dir).filter(
            pl.col("league_id") == league_id
        )
    except FileNotFoundError:  # nothing archived yet
        snaps = pl.DataFrame(schema=store.SCHEMAS["proj_snapshots"])
    weeks = sorted(snaps["week"].unique().to_list())
    empty = ENGINE_SCHEMAS["scorecard"]
    no_counts = dict.fromkeys(
        ("games", "scored", "not_final", "no_kickoff", "no_snapshot", "sleeper_missing"), 0
    )
    if snaps.is_empty():
        return Scorecard(pl.DataFrame(schema=empty), no_counts, [], [], False, None)
    baseline = store.read_table("proj_baseline", "derived", data_dir).filter(
        pl.col("league_id") == league_id
    )
    meta = baseline.select(*KEY, "team", "position")
    games = snaps.select(*KEY).unique().join(meta, on=KEY, how="left")
    actuals = (
        store.read_table("player_points", "derived", data_dir)
        .filter(pl.col("league_id") == league_id)
        .select(*KEY, "points")
    )
    kick = _kickoff_frame(games, store.read_table("nfl_schedules", "raw", data_dir))
    league = (
        store.read_table("leagues", "raw", data_dir)
        .filter(pl.col("league_id") == league_id)
        .row(0, named=True)
    )
    sleeper_archive = store.read_table("sleeper_proj_snapshots", "archive", data_dir)
    id_map = store.read_table("id_map", "derived", data_dir).select("sleeper_id", "gsis_id")
    sleeper = _sleeper_points(sleeper_archive, league, id_map, games)
    scored, excluded = score_games(games, snaps, sleeper, actuals, kick)
    train = baseline.filter(
        (~pl.col("is_future")) & pl.col("has_history") & (pl.col("season") <= TRAIN_END)
    ).drop_nulls("projection")
    scored = add_tiers(scored.with_columns(pl.col("position").fill_null("?")), train)
    table = error_table(
        scored.rename({"gsis_id": "_g"}).select("week", "position", "tier", "actual", *MODELS)
    )
    return Scorecard(
        table,
        excluded,
        weeks,
        sorted(scored["week"].unique().to_list()),
        False,
        str(sleeper_archive["fetched_at"].min()) if sleeper_archive.height else None,
    )
