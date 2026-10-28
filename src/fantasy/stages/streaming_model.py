"""Ridge projection for the K and DEF units that `streaming` projects.

A unit's projection is a ridge regression of its points on trailing features, refit on every
earlier game from FIT_FROM on: its own trailing form and the game's implied total for both kinds;
for K also a dome flag, the spread, home field, the team's trailing offense, the kicker's trailing
field-goal volume and long-kick share, and the opposing defense's trailing points allowed.
`research/kdef_features_check.py` holds the test (docs/decisions.md, 2026-10-27).

Every trailing feature is an exponentially weighted mean of the unit's earlier games, shrunk toward
the mean of all earlier rows, so no feature sees the game it predicts or anything later. A row with
no values (a game not yet played) reads the state but does not change it, so every week ahead gets
the state as of the last game played.
"""

from collections.abc import Sequence

import numpy as np
import polars as pl

TRAIL_HALF_LIFE = 6.0  # games
TRAIL_SHRINK = 3.0  # pseudo-games of the earlier-rows mean
RIDGE_LAMBDA = 10.0  # on standardized features; not tuned
FIT_FROM = 2019  # earlier seasons are only warm-up for the trailing features
MIN_FIT_ROWS = 200  # fewer complete earlier rows and the caller keeps the plain projection
TEAM_KEY = ["team", "season", "week"]
TEAM_STATS = (
    "sacks_suffered", "passing_interceptions", "attempts", "def_sacks", "def_interceptions",
)  # fmt: skip
TEAM_EFFICIENCY = ("pass_epa", "sack_rate")
TEAM_PACE = ("plays", "pass_oe", "team_epa")
LONG_KICK_COLUMNS = (
    "fg_made_40_49", "fg_made_50_59", "fg_made_60_",
    "fg_missed_40_49", "fg_missed_50_59", "fg_missed_60_",
)  # fmt: skip
KICKER_TRAILED = ("fg_att", "pat_att", "long_share")
TEAM_TRAILED = (*TEAM_STATS, *TEAM_EFFICIENCY, *TEAM_PACE, "points_against", "points_for")
DEF_FEATURES = ["form", "implied"]
K_FEATURES = [
    "form", "implied", "dome", "spread", "is_home",
    "d_team_epa_tr", "d_plays_tr", "d_pass_oe_tr", "d_points_for_tr",
    "fg_att_tr", "long_share_tr", "pat_att_tr",
    "o_points_against_tr", "o_def_sacks_tr",
]  # fmt: skip


def trailing(df: pl.DataFrame, key: str, cols: Sequence[str]) -> pl.DataFrame:
    """Adds `<col>_tr`: the unit's earlier games, exponentially weighted, shrunk toward the mean of
    all rows in earlier weeks. A week's rows are all read before any of them updates the state."""
    decay = 0.5 ** (1 / TRAIL_HALF_LIFE)
    ordered = df.sort("season", "week").with_row_index("_i")
    values = ordered.select(cols).to_numpy().astype(float)
    keys = ordered[key].to_list()
    weeks = list(zip(ordered["season"].to_list(), ordered["week"].to_list(), strict=True))
    out = np.full(values.shape, np.nan)
    state: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    total, count = np.zeros(len(cols)), np.zeros(len(cols))
    zero = (np.zeros(len(cols)), np.zeros(len(cols)))
    start = 0
    while start < len(weeks):
        end = start
        while end < len(weeks) and weeks[end] == weeks[start]:
            end += 1
        mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
        for i in range(start, end):
            s, w = state.get(keys[i], zero)
            out[i] = (s + TRAIL_SHRINK * mean) / (w + TRAIL_SHRINK)
        for i in range(start, end):
            present = ~np.isnan(values[i])
            if not present.any():
                continue
            s, w = state.get(keys[i], zero)
            v = np.where(present, values[i], 0.0)
            state[keys[i]] = (s * decay + v, w * decay + present)
            total += v
            count += present
        start = end
    fresh = [pl.Series(f"{c}_tr", out[:, j]) for j, c in enumerate(cols)]
    return ordered.with_columns(fresh).sort("_i").drop("_i")


def with_form(history: pl.DataFrame, upcoming: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Both frames with `form`, the unit's trailing points. `history` has unit, season, week and
    points; `upcoming` has unit, season and week. Games ahead share the unit's current form."""
    ahead = upcoming.select("unit", "season", "week").with_columns(
        pl.lit(None, dtype=pl.Float64).alias("points")
    )
    done = history.select("unit", "season", "week", "points")
    both = pl.concat(
        [
            done.with_columns(pl.lit(False).alias("_ahead")),
            ahead.with_columns(pl.lit(True).alias("_ahead")),
        ]
    )
    formed = trailing(both, "unit", ["points"]).select(
        "unit", "season", "week", "_ahead", pl.col("points_tr").alias("form")
    )
    keys = ["unit", "season", "week"]
    return (
        history.join(formed.filter(~pl.col("_ahead")).drop("_ahead"), on=keys, how="left"),
        upcoming.join(formed.filter(pl.col("_ahead")).drop("_ahead"), on=keys, how="left"),
    )


def team_trailing(
    stats: pl.DataFrame, efficiency: pl.DataFrame, pace: pl.DataFrame, games: pl.DataFrame
) -> pl.DataFrame:
    """Trailing team features before each regular-season team-game, unplayed games included.
    `games` (team_games) must already use the stats team codes. Carries the game's spread and
    home flag."""
    spine = games.filter(pl.col("game_type") == "REG").select(
        *TEAM_KEY, "points_against", "points_for", "spread", "is_home"
    )
    table = (
        spine.join(
            stats.filter(pl.col("season_type") == "REG").select(*TEAM_KEY, *TEAM_STATS),
            on=TEAM_KEY,
            how="left",
        )
        .join(efficiency.select(*TEAM_KEY, *TEAM_EFFICIENCY), on=TEAM_KEY, how="left")
        .join(pace.select(*TEAM_KEY, *TEAM_PACE), on=TEAM_KEY, how="left")
    )
    return trailing(table, "team", TEAM_TRAILED).select(
        *TEAM_KEY,
        "spread",
        pl.col("is_home").cast(pl.Float64),
        *[f"{c}_tr" for c in TEAM_TRAILED],
    )


def kicker_trailing(player_stats: pl.DataFrame, ahead: pl.DataFrame) -> pl.DataFrame:
    """Trailing field-goal attempts, extra-point attempts and share of kicks from 40 yards or
    more, before each kicker game and for the games `ahead` (gsis_id, season, week)."""
    long_kicks = sum(pl.col(c).fill_null(0) for c in LONG_KICK_COLUMNS)
    done = player_stats.filter(pl.col("position") == "K").select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        pl.col("fg_att").cast(pl.Float64),
        pl.col("pat_att").cast(pl.Float64),
        pl.when(pl.col("fg_att") > 0).then(long_kicks / pl.col("fg_att")).alias("long_share"),
    )
    game = ["gsis_id", "season", "week"]
    pending = (
        ahead.select(game)
        .join(done.select(game), on=game, how="anti")
        .with_columns(pl.lit(None, dtype=pl.Float64).alias(c) for c in KICKER_TRAILED)
    )  # a game already played keeps its own row, whose features are pre-game
    table = trailing(pl.concat([done, pending]), "gsis_id", KICKER_TRAILED)
    return table.select("gsis_id", "season", "week", *[f"{c}_tr" for c in KICKER_TRAILED])


def add_team_features(rows: pl.DataFrame, teams: pl.DataFrame) -> pl.DataFrame:
    """Own (`d_`) and opposing (`o_`) trailing team features. `rows` has team, opponent_team,
    season and week; `spread` and `is_home` come from the team's own game."""
    trailed = [c for c in teams.columns if c.endswith("_tr")]
    own = teams.select(*TEAM_KEY, "spread", "is_home", *trailed).rename(
        {c: f"d_{c}" for c in trailed}
    )
    them = teams.select(*TEAM_KEY, *trailed).rename(
        {"team": "opponent_team", **{c: f"o_{c}" for c in trailed}}
    )
    return rows.join(own, on=TEAM_KEY, how="left").join(
        them, on=["opponent_team", "season", "week"], how="left"
    )


def ridge_predict(x_fit: np.ndarray, y: np.ndarray, x_new: np.ndarray) -> np.ndarray:
    """Ridge on standardized features with an unpenalized intercept."""
    mu, sd = x_fit.mean(axis=0), x_fit.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    z, z_new = (x_fit - mu) / sd, (x_new - mu) / sd
    centre = float(y.mean())
    coef = np.linalg.solve(z.T @ z + RIDGE_LAMBDA * np.eye(z.shape[1]), z.T @ (y - centre))
    return centre + z_new @ coef


def project(
    history: pl.DataFrame, upcoming: pl.DataFrame, features: Sequence[str]
) -> pl.DataFrame | None:
    """`upcoming` with a `projection` column, fit on the complete `history` rows (points and every
    feature) from FIT_FROM on. A feature missing in an upcoming row counts as the fit mean. None
    when fewer than MIN_FIT_ROWS rows are complete."""
    usable = history.filter(pl.col("season") >= FIT_FROM).with_columns(
        pl.col(c).fill_nan(None) for c in features
    )
    fit = usable.drop_nulls([*features, "points"])
    if fit.height < MIN_FIT_ROWS:
        return None
    fills = {f: float(fit[f].mean()) for f in features}  # type: ignore[arg-type]
    new = upcoming.select(
        [pl.col(f).fill_nan(None).fill_null(fills[f]) for f in features]
    ).to_numpy()
    values = ridge_predict(fit.select(features).to_numpy(), fit["points"].to_numpy(), new)
    return upcoming.with_columns(pl.Series("projection", values))


def backtest_rmse(
    rows: pl.DataFrame, features: Sequence[str], scored_from: int
) -> tuple[float, float]:
    """RMSE of the walk-forward projection and of the mean of earlier points, on the rows from
    season `scored_from` on; each week is fit on earlier weeks only."""
    model_errors, mean_errors = [], []
    for (season, week), games in rows.filter(pl.col("season") >= scored_from).group_by(
        "season", "week"
    ):
        earlier = rows.filter(
            (pl.col("season") < season) | ((pl.col("season") == season) & (pl.col("week") < week))
        )
        out = project(earlier, games, features)
        if out is None:
            continue
        actual = games["points"].to_numpy()
        model_errors += list(actual - out["projection"].to_numpy())
        mean_errors += list(actual - float(earlier["points"].mean()))  # type: ignore[arg-type]
    if not model_errors:
        raise ValueError(f"no games from season {scored_from} to score")
    return (
        float(np.sqrt(np.mean(np.square(model_errors)))),
        float(np.sqrt(np.mean(np.square(mean_errors)))),
    )
