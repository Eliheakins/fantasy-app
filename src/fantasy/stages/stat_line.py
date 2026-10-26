"""Chance that an active player-game has a stat line: the first part of the two-part projection.

About 6 to 12% of skill `player_points` rows are stat-less appearances: every stat 0 and no
`nfl_ff_opportunity` row (special-teams snaps, or a couple of offensive snaps). The learned model
trains only on games with a stat line, so its projection is E[points | stat line]. With
`stat_line_model` on, `learn` multiplies it by q = P(stat line | active), so `proj_learned` holds
E[points | active], where active means the player has a `player_points` row (he dressed and got
on the field). research/hurdle_check.py and docs/decisions.md have the held-out test.

q comes from a classifier on pre-game features: weighted averages (half-life 4 games, strictly
before the game) of offensive and special-teams snap share, target share, targets, carries and
the stat-line rate over earlier active games; the last snap share, games played and weeks since
the last active game; the game's depth rank; position. Past games are scored walk-forward by
season, like `learn`. Every future game of a player gets the q of his next game from a model fit
on all history: later weeks have no depth chart, and the gap since his last game would read as
missed games.
"""

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier

from fantasy.stages import learn
from fantasy.stages.project import FIRST_PROJECTED_SEASON, POSITIONS

KEY = ["gsis_id", "season", "week"]
LAGGED = ["snap", "st", "tshare", "tgt", "car", "statline"]
FEATURES = [f"h_{c}" for c in LAGGED] + ["snap_last", "n_prior", "weeks_since", "depth_rank"]
WEEKS_PER_SEASON = 18  # to count weeks missed across a season boundary


def active_rows(points: pl.DataFrame, exp: pl.DataFrame) -> pl.DataFrame:
    """KEY, position, statline (1.0 when the game has an expected-points row) for every skill
    `player_points` row. Rows do not depend on the league, so the first league's are used."""
    lid = min(points["league_id"].unique().to_list())
    rows = points.filter((pl.col("league_id") == lid) & pl.col("position").is_in(POSITIONS))
    have = exp.filter(pl.col("league_id") == lid).select(KEY).with_columns(statline=pl.lit(1.0))
    return (
        rows.select(*KEY, "position")
        .unique(KEY, keep="first", maintain_order=True)
        .join(have, on=KEY, how="left")
        .with_columns(pl.col("statline").fill_null(0.0))
    )


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


def history_table(active: pl.DataFrame, usage: pl.DataFrame) -> pl.DataFrame:
    """One row per active game with its usage (no opportunity row: 0 targets and carries), the
    running game count, a week counter and the snap share again as `snap_last`."""
    return (
        active.select(*KEY, "statline")
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
    """targets (KEY, position, ...) with FEATURES from active games strictly before each game and
    the game's own depth chart."""
    out = learn.lag_asof(targets, history, "gsis_id", LAGGED, "h")
    out = learn.latest_asof(out, history, "gsis_id", ["snap_last", "n_prior", "when"], shift=1)
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


def fit_predict(train: pl.DataFrame, test: pl.DataFrame) -> np.ndarray:
    """q for `test` from a classifier fit on `train` (which has `statline`)."""
    y = train["statline"].to_numpy()
    if test.is_empty() or len(np.unique(y)) < 2:  # nothing to score, or nothing to learn
        return np.full(test.height, float(y.mean()) if len(y) else 1.0)
    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=0,
    )
    model.fit(design(train), y)
    return model.predict_proba(design(test))[:, 1]


def history_chance(feats: pl.DataFrame) -> pl.DataFrame:
    """KEY, q for every past game from FIRST_PROJECTED_SEASON, each season from a model fit on
    the seasons `learn` would train on for it."""
    usable = feats.filter(pl.col("season") >= FIRST_PROJECTED_SEASON)
    seasons = sorted(usable["season"].unique().to_list())
    parts = []
    for season in seasons:
        train = usable.filter(pl.col("season").is_in(learn.train_seasons(season, seasons)))
        test = usable.filter(pl.col("season") == season)
        parts.append(test.select(KEY).with_columns(pl.Series("q", fit_predict(train, test))))
    return pl.concat(parts)


def next_game_features(
    future: pl.DataFrame, history: pl.DataFrame, depth: pl.DataFrame, current_week: int
) -> pl.DataFrame:
    """FEATURES at each player's first future game. A player whose next game is after this week
    (a bye) gets the latest depth chart, since his game's chart is not out yet."""
    first = future.sort("week").unique("gsis_id", keep="first").select(*KEY, "position")
    chart = depth.select(*KEY, "depth_rank").unique(KEY, keep="first", maintain_order=True)
    latest = learn.latest_asof(first.select(KEY), chart, "gsis_id", ["depth_rank"]).rename(
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


def chances(
    exp: pl.DataFrame,
    points: pl.DataFrame,
    raw: dict[str, pl.DataFrame],
    future: pl.DataFrame,
    current_week: int,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(KEY, q) for past games and (gsis_id, q) for future ones. raw: opp, snaps, stats, depth."""
    active = active_rows(points, exp)
    history = history_table(active, usage_frame(raw["opp"], raw["snaps"], raw["stats"]))
    feats = features(active, history, raw["depth"])
    return history_chance(feats), next_game_chance(
        feats, history, raw["depth"], future, current_week
    )


def scale(frame: pl.DataFrame, chance: pl.DataFrame, on: list[str]) -> pl.DataFrame:
    """`frame` with its projection multiplied by q (joined on `on`); every row must have one."""
    joined = frame.join(chance.select(*on, "q"), on=on, how="left")
    missing = int(joined["q"].null_count())
    if missing:
        raise ValueError(f"{missing} projection rows have no stat-line chance")
    return joined.with_columns(pl.col("projection") * pl.col("q")).drop("q")
