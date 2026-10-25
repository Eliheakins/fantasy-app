"""Positional team grades: starter strength blended with bench depth, ranked and lettered."""

import polars as pl

# Starters decide most weeks; depth only matters when a starter is out, so it counts a third as
# much (75/25, a judgement, not fitted).
STARTER_WEIGHT = 0.75
DEPTH_WEIGHT = 0.25
GRADE_LETTERS = "ABCDF"  # one per fifth of the league, strongest first
OVERALL = "overall"
MIN_SPREAD = 1e-9


def grade_for_rank(rank: int, teams: int) -> str:
    """Letter for a 1-based rank among `teams`: top fifth A, then B, C, D, bottom fifth F.
    Tied teams share the best rank of the tie, so they share a grade."""
    return GRADE_LETTERS[min((rank - 1) * 5 // teams, 4)]


def _z(column: str) -> pl.Expr:
    """Standard score within a position; 0 for everyone when the teams do not differ."""
    spread = pl.col(column).std().over("position")
    return (
        pl.when(spread.fill_null(0.0) < MIN_SPREAD)
        .then(0.0)
        .otherwise((pl.col(column) - pl.col(column).mean().over("position")) / spread)
    )


def team_grades(
    strength: pl.DataFrame,
    depth: pl.DataFrame,
    teams: pl.DataFrame,
    starter_weight: float = STARTER_WEIGHT,
    depth_weight: float = DEPTH_WEIGHT,
) -> pl.DataFrame:
    """One row per team and position plus an `overall` row.

    `strength` is roster_id, position, vor_per_week (starters); `depth` is roster_id, position,
    depth_per_week; `teams` is roster_id, team_name, is_me. A position's score is
    z(starters) * starter_weight + z(depth) * depth_weight. The overall row scores the summed
    points a week the same way (starters plus depth scaled by depth_weight / starter_weight)."""
    cells = strength.join(depth, on=["roster_id", "position"]).with_columns(
        (_z("vor_per_week") * starter_weight + _z("depth_per_week") * depth_weight).alias("score")
    )
    total = cells.group_by("roster_id").agg(
        pl.col("vor_per_week").sum(),
        pl.col("depth_per_week").sum(),
        pl.lit(OVERALL).alias("position"),
    )
    total = total.with_columns(
        (pl.col("vor_per_week") + pl.col("depth_per_week") * depth_weight / starter_weight).alias(
            "score"
        )
    )
    n = teams.height
    return (
        pl.concat([cells.select(total.columns), total])
        .with_columns(
            pl.col("score")
            .rank("min", descending=True)
            .over("position")
            .cast(pl.Int64)
            .alias("rank")
        )
        .join(teams, on="roster_id")
        .with_columns(
            pl.col("rank")
            .map_elements(lambda r: grade_for_rank(r, n), return_dtype=pl.String)
            .alias("grade")
        )
        .select(
            "roster_id",
            "team_name",
            "is_me",
            "position",
            "vor_per_week",
            "depth_per_week",
            "score",
            "rank",
            "grade",
        )  # fmt: skip
        .sort(["position", "rank", "roster_id"])
    )
