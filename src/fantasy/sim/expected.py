"""Expected points per player-game under a league's scoring, from nflverse opportunity rows."""

import json
import warnings

import polars as pl

from fantasy.scoring import expected_points_expr
from fantasy.store import SKILL

MAX_UNSCORED_SHARE = 0.05  # expected-points rows with no scored row (a position label differs)


def expected_frame(
    opp: pl.DataFrame, player_points: pl.DataFrame, leagues: pl.DataFrame
) -> pl.DataFrame:
    """One row per league and player-game: expected points and actual points."""
    frames = []
    for lg in leagues.iter_rows(named=True):
        actual = player_points.filter(pl.col("league_id") == lg["league_id"]).select(
            "gsis_id", "season", "week", "points"
        )
        scoring = json.loads(lg["scoring_settings"])
        expected = (
            opp.filter(pl.col("position").is_in(SKILL))
            .select(
                pl.col("player_id").alias("gsis_id"),
                "season",
                "week",
                "position",
                pl.col("posteam").alias("team"),
                expected_points_expr(scoring).alias("exp_pts"),
            )
            .unique(subset=["gsis_id", "season", "week"], keep="first", maintain_order=True)
        )
        # an expected-points row with no scored row (nflverse labels the position differently in
        # the two sources, e.g. a CB who plays WR) has no actual points: drop it, not score it 0
        matched = expected.join(actual, on=["gsis_id", "season", "week"], how="inner")
        dropped = expected.height - matched.height
        if dropped:
            warnings.warn(
                f"expected_frame: league {lg['league_id']}: {dropped} unscored rows dropped",
                stacklevel=2,
            )
        if dropped > MAX_UNSCORED_SHARE * expected.height:
            raise ValueError(f"{dropped} of {expected.height} expected-points rows have no points")
        frames.append(matched.with_columns(pl.lit(lg["league_id"]).alias("league_id")))
    return pl.concat(frames)
