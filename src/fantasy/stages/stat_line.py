"""Chance that a played game has a stat line: the first part of the two-part projection.

A game is played when the player had offensive snaps (nfl_snaps) or has a `player_points` row. Some
played games have no stat line: a `player_points` row with every stat 0 and no
`nfl_ff_opportunity` row (special teams, a couple of snaps), or snaps and no row at all. Both score
0. The learned model trains only on games with a stat line, so its projection is E[points | stat
line]. With `stat_line_model` on, `learn` multiplies it by q = P(stat line | played), so
`proj_learned` holds E[points | played]; availability's chance of playing (any offensive snaps) is
the same event, so p * q * E counts nothing twice. research/hurdle_check.py and
docs/decisions.md have the held-out tests.

q comes from a classifier (mean of three seeds, floored at Q_FLOOR) on pre-game features: weighted
averages (half-life 4 games, strictly before the game) of offensive and special-teams snap share,
target share, targets, carries and the stat-line rate over earlier played games; the last snap
share, games played and weeks since the last played game; the game's depth rank; position. Past
games are scored walk-forward by season, like `learn`; played games without a stat line get a
learned projection too, so the spread shapes are fit on every played game. A player's next game
gets q from a model fit on all history; his later games get the higher of that and the stat-line
rate of his position and latest depth rank (their own features are not known yet, and a long
absence before the next game would otherwise drag every later game down). `learn` writes q to the
`stat_line` table (`fantasy/stat_line_table.py`): the injury table's chance of playing counts
games with touches or targets, the stat-line event itself, so the injury layer and the `injuries`
stage take q back out there.
"""

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier

from fantasy.stages.lags import lag_asof, latest_asof, train_seasons
from fantasy.stages.project import FIRST_PROJECTED_SEASON, POSITIONS

KEY = ["gsis_id", "season", "week"]
LAGGED = ["snap", "st", "tshare", "tgt", "car", "statline"]
FEATURES = [f"h_{c}" for c in LAGGED] + ["snap_last", "n_prior", "weeks_since", "depth_rank"]
WEEKS_PER_SEASON = 18  # to count weeks missed across a season boundary
SEEDS = (0, 1, 2)  # averaged: early stopping draws a seeded validation split (decisions)
MIN_CELL_ROWS = 30  # a position-depth cell with fewer games uses the position's rate
Q_FLOOR = 0.01  # q is never 0, so a projection can always be divided by it


def played_rows(
    points: pl.DataFrame, exp: pl.DataFrame, snaps: pl.DataFrame, opp: pl.DataFrame
) -> pl.DataFrame:
    """KEY, position, team, statline for every played skill game: a `player_points` row (statline
    1.0 when it has an expected-points row), or offensive snaps with no row (statline 0, 0
    points). A snap game with an opportunity row but no scored row (nflverse labels the position
    differently in the two sources) cannot be scored and is left out. Rows do not depend on the
    league, so the first league's are used."""
    lid = min(points["league_id"].unique().to_list())
    scored = (
        points.filter((pl.col("league_id") == lid) & pl.col("position").is_in(POSITIONS))
        .select(*KEY, "position", "team")
        .unique(KEY, keep="first", maintain_order=True)
    )
    have = exp.filter(pl.col("league_id") == lid).select(KEY).with_columns(statline=pl.lit(1.0))
    with_opp = opp.select(pl.col("player_id").alias("gsis_id"), "season", "week")
    snap_only = (
        snaps.filter(
            pl.col("gsis_id").is_not_null()
            & (pl.col("offense_snaps") > 0)
            & pl.col("position").is_in(POSITIONS)
        )
        .select(*KEY, "position", "team")
        .unique(KEY, keep="first", maintain_order=True)
        .join(scored.select(KEY), on=KEY, how="anti")
        .join(with_opp, on=KEY, how="anti")
    )
    return (
        pl.concat([scored.join(have, on=KEY, how="left"), snap_only], how="diagonal_relaxed")
        .with_columns(pl.col("statline").fill_null(0.0))
        .select(*KEY, "position", "team", "statline")
    )


def statless_targets(played: pl.DataFrame, league_id: str) -> pl.DataFrame:
    """league_id, gsis_id, season, week, position, team of the played games with no stat line,
    from FIRST_PROJECTED_SEASON: `learn` projects them but never trains on them."""
    return played.filter(
        (pl.col("statline") == 0.0) & (pl.col("season") >= FIRST_PROJECTED_SEASON)
    ).select(pl.lit(league_id).alias("league_id"), *KEY, "position", "team")


def usage_frame(opp: pl.DataFrame, snaps: pl.DataFrame, stats: pl.DataFrame) -> pl.DataFrame:
    """KEY, snap, st, tshare, tgt, car per player-game, from the raw nflverse tables."""
    volume = opp.select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        pl.col("rec_attempt").cast(pl.Float64).alias("tgt"),
        pl.col("rush_attempt").cast(pl.Float64).alias("car"),
    ).unique(KEY, keep="first", maintain_order=True)
    snap = (
        snaps.filter(pl.col("gsis_id").is_not_null())
        .select(
            *KEY,
            pl.col("offense_pct").cast(pl.Float64).alias("snap"),
            pl.col("st_pct").cast(pl.Float64).alias("st"),
        )
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
    return snap.join(share, on=KEY, how="full", coalesce=True).join(
        volume, on=KEY, how="full", coalesce=True
    )


def history_table(played: pl.DataFrame, usage: pl.DataFrame) -> pl.DataFrame:
    """One row per played game with its usage (no opportunity row: 0 targets and carries), the
    running game count, a week counter and the snap share again as `snap_last`."""
    return (
        played.select(*KEY, "statline")
        .join(usage, on=KEY, how="left")
        .with_columns(pl.col("tgt", "car").fill_null(0.0))
        .sort("gsis_id", "season", "week")
        .with_columns(
            pl.int_range(1, pl.len() + 1).over("gsis_id").cast(pl.Float64).alias("n_prior"),
            (pl.col("season") * WEEKS_PER_SEASON + pl.col("week")).cast(pl.Float64).alias("when"),
            pl.col("snap").alias("snap_last"),
        )
    )


def features(targets: pl.DataFrame, history: pl.DataFrame, depth: pl.DataFrame) -> pl.DataFrame:
    """targets (KEY, position, ...) with FEATURES from played games strictly before each game and
    the game's own depth chart."""
    out = lag_asof(targets, history, "gsis_id", LAGGED, "h")
    out = latest_asof(out, history, "gsis_id", ["snap_last", "n_prior", "when"], shift=1)
    chart = depth.select(*KEY, "depth_rank").unique(KEY, keep="first", maintain_order=True)
    return (
        out.join(chart, on=KEY, how="left")
        .with_columns(
            (pl.col("season") * WEEKS_PER_SEASON + pl.col("week") - pl.col("when") - 1).alias(
                "weeks_since"
            ),
            pl.col("n_prior").fill_null(0.0),
        )
        .drop("when")
    )


def design(frame: pl.DataFrame) -> np.ndarray:
    numeric = [frame[c].cast(pl.Float64).to_numpy() for c in FEATURES]
    onehot = [(frame["position"] == p).cast(pl.Float64).to_numpy() for p in POSITIONS]
    return np.column_stack(numeric + onehot)


def fit_predict(
    train: pl.DataFrame, test: pl.DataFrame, seeds: tuple[int, ...] = SEEDS
) -> np.ndarray:
    """q for `test`: the mean over `seeds` of a classifier fit on `train` (which has `statline`),
    floored at Q_FLOOR."""
    y = train["statline"].to_numpy()
    if test.is_empty() or len(np.unique(y)) < 2:  # nothing to score, or nothing to learn
        rate = float(y.mean()) if len(y) else 1.0
        return np.full(test.height, max(rate, Q_FLOOR))
    x_train, x_test = design(train), design(test)
    preds = []
    for seed in seeds:
        model = HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.05,
            max_leaf_nodes=15,
            min_samples_leaf=80,
            l2_regularization=5.0,
            random_state=seed,
        )
        preds.append(model.fit(x_train, y).predict_proba(x_test)[:, 1])
    return np.clip(np.mean(preds, axis=0), Q_FLOOR, 1.0)


def history_chance(feats: pl.DataFrame, seeds: tuple[int, ...] = SEEDS) -> pl.DataFrame:
    """KEY, q for every past game from FIRST_PROJECTED_SEASON, each season from a model fit on
    the seasons `learn` would train on for it."""
    usable = feats.filter(pl.col("season") >= FIRST_PROJECTED_SEASON)
    seasons = sorted(usable["season"].unique().to_list())
    parts = []
    for season in seasons:
        train = usable.filter(pl.col("season").is_in(train_seasons(season, seasons)))
        test = usable.filter(pl.col("season") == season)
        parts.append(test.select(KEY).with_columns(pl.Series("q", fit_predict(train, test, seeds))))
    return pl.concat(parts)


def next_game_features(
    future: pl.DataFrame, history: pl.DataFrame, depth: pl.DataFrame, current_week: int
) -> pl.DataFrame:
    """FEATURES at each player's first future game. A player whose next game is after this week
    (a bye) gets the latest depth chart, since his game's chart is not out yet."""
    first = future.sort("week").unique("gsis_id", keep="first").select(*KEY, "position")
    chart = depth.select(*KEY, "depth_rank").unique(KEY, keep="first", maintain_order=True)
    latest = latest_asof(first.select(KEY), chart, "gsis_id", ["depth_rank"]).rename(
        {"depth_rank": "_latest"}
    )
    return (
        features(first, history, depth)
        .join(latest, on=KEY, how="left")
        .with_columns(
            pl.when(pl.col("week") > current_week)
            .then(pl.coalesce("depth_rank", "_latest"))
            .otherwise(pl.col("depth_rank"))
            .alias("depth_rank")
        )
        .drop("_latest")
    )


def next_game_chance(
    feats: pl.DataFrame,
    history: pl.DataFrame,
    depth: pl.DataFrame,
    future: pl.DataFrame,
    current_week: int,
) -> pl.DataFrame:
    """gsis_id, q of each player's next game, from a model fit on all past games."""
    test = next_game_features(future, history, depth, current_week)
    train = feats.filter(pl.col("season") >= FIRST_PROJECTED_SEASON)
    return test.select("gsis_id").with_columns(pl.Series("q", fit_predict(train, test)))


def depth_cell() -> pl.Expr:
    """`d_cell`: the depth rank as a cell label, 1, 2, 3, 4+ or none (not on the chart)."""
    rank = pl.col("depth_rank")
    return (
        pl.when(rank.is_null())
        .then(pl.lit("none"))
        .when(rank >= 4)
        .then(pl.lit("4+"))
        .otherwise(rank.cast(pl.Int64).cast(pl.String))
        .alias("d_cell")
    )


def cell_chance(rows: pl.DataFrame, min_rows: int = MIN_CELL_ROWS) -> pl.DataFrame:
    """position, d_cell, q_cell: the stat-line rate of each position and depth rank (1, 2, 3, 4+,
    none) with at least `min_rows` games. rows: position, depth_rank, statline."""
    return (
        rows.with_columns(depth_cell())
        .group_by("position", "d_cell")
        .agg(pl.col("statline").mean().alias("q_cell"), pl.len().alias("n"))
        .filter(pl.col("n") >= min_rows)
        .drop("n")
    )


def position_chance(rows: pl.DataFrame) -> dict[str, float]:
    """Position -> stat-line rate, the fallback for a position-depth cell with too few games."""
    rates = rows.group_by("position").agg(pl.col("statline").mean())
    return dict(zip(rates["position"], rates["statline"], strict=True))


def future_chance(
    future: pl.DataFrame,
    nxt: pl.DataFrame,
    cells: pl.DataFrame,
    positions: dict[str, float],
    depth: pl.DataFrame,
) -> pl.DataFrame:
    """KEY, q for every future game: the next game's q (nxt: gsis_id, q) for a player's first
    game, the higher of it and his position-depth rate (latest chart) for later ones."""
    chart = depth.select(*KEY, "depth_rank").unique(KEY, keep="first", maintain_order=True)
    rows = latest_asof(
        future.select(*KEY, "position").unique(KEY, keep="first"), chart, "gsis_id", ["depth_rank"]
    )
    fallback = pl.col("position").replace_strict(positions, default=None, return_dtype=pl.Float64)
    return (
        rows.with_columns(depth_cell())
        .join(cells, on=["position", "d_cell"], how="left")
        .join(nxt.select("gsis_id", pl.col("q").alias("_next")), on="gsis_id", how="left")
        .with_columns(
            pl.when(pl.col("week") == pl.col("week").min().over("gsis_id"))
            .then(pl.col("_next"))
            .otherwise(pl.max_horizontal("_next", pl.coalesce("q_cell", fallback)))
            .clip(Q_FLOOR, 1.0)
            .alias("q")
        )
        .select(*KEY, "q")
    )


def chances(
    exp: pl.DataFrame,
    points: pl.DataFrame,
    raw: dict[str, pl.DataFrame],
    future: pl.DataFrame,
    current_week: int,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(KEY, q) for past games and for future ones. raw: opp, snaps, stats, depth."""
    played = played_rows(points, exp, raw["snaps"], raw["opp"])
    history = history_table(played, usage_frame(raw["opp"], raw["snaps"], raw["stats"]))
    feats = features(played, history, raw["depth"])
    nxt = next_game_chance(feats, history, raw["depth"], future, current_week)
    fit_rows = feats.filter(pl.col("season") >= FIRST_PROJECTED_SEASON)
    later = future_chance(
        future, nxt, cell_chance(fit_rows), position_chance(fit_rows), raw["depth"]
    )
    return history_chance(feats), later
