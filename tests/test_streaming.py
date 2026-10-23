import numpy as np
import polars as pl

from fantasy.stages.streaming import (
    defense_points_frame,
    fit_context,
    shrunk_form,
    tier_expr,
    tier_terms,
)

SCORING = {
    "sack": 1.0,
    "int": 2.0,
    "fum_rec": 2.0,
    "def_td": 6.0,
    "pts_allow_0": 10.0,
    "pts_allow_1_6": 7.0,
    "pts_allow_7_13": 4.0,
    "pts_allow_35p": -4.0,
    "yds_allow_0_100": 5.0,
    "yds_allow_300_349": 0.0,
    "yds_allow_550p": -7.0,
}


def test_tier_terms_parse_ranges_open_ends_and_drop_zero_weights():
    terms = tier_terms(SCORING, "pts_allow")
    assert (0, 0, 10.0) in terms and (1, 6, 7.0) in terms and (35, 10**6, -4.0) in terms
    assert all(w != 0 for _, _, w in tier_terms(SCORING, "yds_allow"))


def test_tier_expr_picks_the_matching_bracket():
    frame = pl.DataFrame({"allowed": [0, 3, 13, 20, 40]})
    out = frame.select(tier_expr("allowed", tier_terms(SCORING, "pts_allow")))["literal"]
    assert out.to_list() == [10.0, 7.0, 4.0, 0.0, -4.0]


def _stats(**overrides: float) -> pl.DataFrame:
    zero = {
        "def_sacks": 0.0,
        "def_interceptions": 0.0,
        "fumble_recovery_opp": 0.0,
        "def_fumbles_forced": 0.0,
        "def_safeties": 0.0,
        "def_fg_blocks": 0.0,
        "def_pat_blocks": 0.0,
        "def_punt_blocks": 0.0,
        "def_tds": 0.0,
        "special_teams_tds": 0.0,
        "passing_yards": 200.0,
        "rushing_yards": 100.0,
    }
    rows = [
        {"team": "AAA", "opponent_team": "BBB", "season": 2026, "week": 1, "season_type": "REG"}
        | zero
        | overrides,
        {"team": "BBB", "opponent_team": "AAA", "season": 2026, "week": 1, "season_type": "REG"}
        | zero
        | {"passing_yards": 50.0, "rushing_yards": 30.0},
    ]
    return pl.DataFrame(rows)


def _games(points_against_aaa: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2026, 2026],
            "week": [1, 1],
            "team": ["AAA", "BBB"],
            "points_against": [points_against_aaa, 20],
            "team_implied": [21.0, 24.0],
            "opp_implied": [24.0, 21.0],
            "roof": ["dome", "dome"],
        }
    )


def test_defense_scores_plays_and_the_points_and_yards_allowed_tiers():
    # 2 sacks + 1 int = 4 points; 10 points allowed = +4; BBB gained 80 yards (0 to 100) = +5
    out = defense_points_frame(
        _stats(def_sacks=2.0, def_interceptions=1.0), _games(10), SCORING, "L"
    )
    row = out.filter(pl.col("team") == "AAA").row(0, named=True)
    assert row["points"] == 4.0 + 4.0 + 5.0


def test_points_allowed_exclude_touchdowns_the_opponent_defense_scored():
    stats = _stats()
    stats = stats.with_columns(
        pl.when(pl.col("team") == "BBB").then(1.0).otherwise(pl.col("def_tds")).alias("def_tds")
    )
    # AAA gave up 7 points, 6 of them on BBB's own pick-six, so 1 offensive point: bracket 1-6
    out = defense_points_frame(stats, _games(7), SCORING, "L")
    assert out.filter(pl.col("team") == "AAA")["points"][0] == 7.0 + 5.0


def test_shrunk_form_leans_on_recent_games_and_on_the_mean_when_data_is_thin():
    assert shrunk_form(np.array([]), 6.0) == 6.0
    one = shrunk_form(np.array([20.0]), 6.0)
    many = shrunk_form(np.full(30, 20.0), 6.0)
    assert 6.0 < one < many < 20.0
    assert shrunk_form(np.array([2.0, 2.0, 20.0]), 6.0) > shrunk_form(
        np.array([20.0, 2.0, 2.0]), 6.0
    )


def test_fit_context_recovers_slope_and_dome_effect():
    rng = np.random.default_rng(0)
    implied = rng.uniform(15, 30, 400)
    dome = rng.random(400) < 0.3
    points = 8 - 0.5 * (implied - implied.mean()) + 1.5 * dome + rng.normal(0, 0.5, 400)
    history = pl.DataFrame(
        {"points": points, "implied": implied, "roof": np.where(dome, "dome", "outdoors")}
    )
    slope, bonus = fit_context(history, "implied")
    assert abs(slope + 0.5) < 0.05 and abs(bonus - 1.5) < 0.2
