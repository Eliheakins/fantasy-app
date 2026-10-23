"""Per-league fantasy scoring: Sleeper scoring_settings applied to nflverse stat lines.

Covers offensive players and kickers. Team defenses need points and yards allowed from
other tables and are scored in stages/streaming.py; their Sleeper keys are listed in DEFENSE_KEYS
so a league that uses them still passes the unknown-key check.
"""

import polars as pl

_FUMBLES_LOST = (
    pl.col("sack_fumbles_lost") + pl.col("rushing_fumbles_lost") + pl.col("receiving_fumbles_lost")
)
# Sum of made field goal distances, from "52;39;58;20".
_FG_YARDS = (
    pl.col("fg_made_list").str.split(";").list.eval(pl.element().cast(pl.Float64)).list.sum()
)

# Sleeper scoring key -> expression over nfl_player_stats columns.
PLAYER_TERMS: dict[str, pl.Expr] = {
    "pass_yd": pl.col("passing_yards"),
    "pass_td": pl.col("passing_tds"),
    "pass_int": pl.col("passing_interceptions"),
    "pass_2pt": pl.col("passing_2pt_conversions"),
    "pass_sack": pl.col("sacks_suffered"),
    "rush_yd": pl.col("rushing_yards"),
    "rush_td": pl.col("rushing_tds"),
    "rush_2pt": pl.col("rushing_2pt_conversions"),
    "rec": pl.col("receptions"),
    "rec_yd": pl.col("receiving_yards"),
    "rec_td": pl.col("receiving_tds"),
    "rec_2pt": pl.col("receiving_2pt_conversions"),
    "fum_lost": _FUMBLES_LOST,
    "st_td": pl.col("special_teams_tds"),
    "xpm": pl.col("pat_made"),
    "xpmiss": pl.col("pat_missed"),
    "fgmiss": pl.col("fg_missed") + pl.col("fg_blocked"),  # Sleeper counts blocked kicks as misses
    "fgm_0_19": pl.col("fg_made_0_19"),
    "fgm_20_29": pl.col("fg_made_20_29"),
    "fgm_30_39": pl.col("fg_made_30_39"),
    "fgm_40_49": pl.col("fg_made_40_49"),
    "fgm_50_59": pl.col("fg_made_50_59"),
    "fgm_60p": pl.col("fg_made_60_"),
    "fgm_yds": _FG_YARDS,
}

# Sleeper scoring key -> expected stat from nflverse's ff_opportunity model (opportunity-adjusted).
EXPECTED_TERMS: dict[str, pl.Expr] = {
    "pass_yd": pl.col("pass_yards_gained_exp"),
    "pass_td": pl.col("pass_touchdown_exp"),
    "pass_int": pl.col("pass_interception_exp"),
    "pass_2pt": pl.col("pass_two_point_conv_exp"),
    "rush_yd": pl.col("rush_yards_gained_exp"),
    "rush_td": pl.col("rush_touchdown_exp"),
    "rush_2pt": pl.col("rush_two_point_conv_exp"),
    "rec": pl.col("receptions_exp"),
    "rec_yd": pl.col("rec_yards_gained_exp"),
    "rec_td": pl.col("rec_touchdown_exp"),
    "rec_2pt": pl.col("rec_two_point_conv_exp"),
}

# Keys for team defense and defensive or special-teams plays. Not scored for offensive players.
DEFENSE_KEYS = {
    "blk_kick",
    "def_2pt",
    "def_st_ff",
    "def_st_fum_rec",
    "def_st_td",
    "def_td",
    "ff",
    "fum_rec",
    "fum_rec_td",
    "int",
    "safe",
    "sack",
    "st_ff",
    "st_fum_rec",
}
DEFENSE_PREFIXES = ("pts_allow_", "yds_allow_")


def check_keys(scoring: dict[str, float]) -> None:
    """Raise if a league gives points for something this module does not score."""
    unknown = sorted(
        key
        for key, weight in scoring.items()
        if weight
        and key not in PLAYER_TERMS
        and key not in DEFENSE_KEYS
        and not key.startswith(DEFENSE_PREFIXES)
    )
    if unknown:
        raise ValueError(f"Sleeper scoring keys with points but no mapping: {unknown}")


def points_expr(scoring: dict[str, float]) -> pl.Expr:
    check_keys(scoring)
    terms = [
        expr.fill_null(0.0) * weight
        for key, expr in PLAYER_TERMS.items()
        if (weight := scoring.get(key, 0.0))
    ]
    return pl.sum_horizontal(*terms).round(2) if terms else pl.lit(0.0)


def expected_points_expr(scoring: dict[str, float]) -> pl.Expr:
    """League-scored expected points from ff_opportunity rows (offense only, no fumbles)."""
    terms = [
        expr.fill_null(0.0) * weight
        for key, expr in EXPECTED_TERMS.items()
        if (weight := scoring.get(key, 0.0))
    ]
    return pl.sum_horizontal(*terms) if terms else pl.lit(0.0)


def score_player_stats(stats: pl.DataFrame, scoring: dict[str, float]) -> pl.DataFrame:
    """Add a `points` column to nfl_player_stats rows under one league's scoring."""
    return stats.with_columns(points_expr(scoring).alias("points"))
