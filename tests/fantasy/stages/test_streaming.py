import numpy as np
import polars as pl

from fantasy.stages import streaming
from fantasy.stages.streaming import (
    DEFENSE_FACTS,
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


def _facts(
    aaa: dict[str, float] | None = None, bbb: dict[str, float] | None = None
) -> pl.DataFrame:
    zero = dict.fromkeys(DEFENSE_FACTS, 0.0)
    rows = [
        {"team": "AAA", "season": 2026, "week": 1} | zero | (aaa or {}),
        {"team": "BBB", "season": 2026, "week": 1} | zero | (bbb or {}),
    ]
    return pl.DataFrame(rows)


def _aaa_points(
    stats: pl.DataFrame, allowed: int, facts: pl.DataFrame, scoring: dict[str, float] = SCORING
) -> float:
    out = defense_points_frame(stats, _games(allowed), scoring, "L", facts)
    return float(out.filter(pl.col("team") == "AAA")["points"][0])


def _with(stats: pl.DataFrame, team: str, column: str, value: float) -> pl.DataFrame:
    return stats.with_columns(
        pl.when(pl.col("team") == team).then(value).otherwise(pl.col(column)).alias(column)
    )


def test_defense_scores_plays_and_the_points_and_yards_allowed_tiers():
    # 2 sacks + 1 int = 4 points; 10 points allowed = +4; BBB gained 80 yards (0 to 100) = +5
    stats = _stats(def_sacks=2.0, def_interceptions=1.0)
    assert _aaa_points(stats, 10, _facts()) == 4.0 + 4.0 + 5.0


def test_points_allowed_exclude_touchdowns_the_opponent_defense_scored():
    stats = _with(_stats(), "BBB", "def_tds", 1.0)
    # AAA gave up 7 points, 6 of them on BBB's own pick-six, so 1 offensive point: bracket 1-6
    assert _aaa_points(stats, 7, _facts()) == 7.0 + 5.0


def test_yards_allowed_are_net_of_the_yards_the_opponent_lost_on_sacks():
    # BBB: 90 passing + 30 rushing = 120 gross (no bracket), less 25 sack yards = 95 (0 to 100)
    stats = _with(_stats(), "BBB", "passing_yards", 90.0)
    assert _aaa_points(stats, 20, _facts(bbb={"sack_yards": -25.0})) == 5.0
    assert _aaa_points(stats, 20, _facts()) == 0.0


def test_fumble_return_touchdowns_score_and_leave_the_opponents_points_allowed():
    # nflverse def_tds counts interception returns only; fumble returns come from play-by-play
    facts = _facts(aaa={"fumble_return_tds": 1.0}, bbb={"fumble_return_tds": 1.0})
    # AAA: its own return TD +6; 7 allowed, 6 of them on BBB's fumble return: bracket 1-6 = +7
    assert _aaa_points(_stats(), 7, facts) == 6.0 + 7.0 + 5.0


def test_special_teams_touchdowns_stay_in_points_allowed():
    # Sleeper charges a kick or punt return TD to the defense on the field's points allowed
    stats = _with(_stats(), "BBB", "special_teams_tds", 1.0)
    assert _aaa_points(stats, 7, _facts()) == 4.0 + 5.0


def test_special_teams_fumbles_score_at_the_special_teams_rates():
    scoring = {"fum_rec": 2.0, "ff": 1.0, "def_st_fum_rec": 1.0, "def_st_ff": 1.0}
    stats = _stats(fumble_recovery_opp=2.0, def_fumbles_forced=2.0)
    facts = _facts(aaa={"st_fumble_recoveries": 1.0, "st_fumbles_forced": 1.0})
    # one defensive recovery (2) and forced fumble (1), one muffed punt recovered and forced (1+1)
    assert _aaa_points(stats, 20, facts, scoring) == 2.0 + 1.0 + 1.0 + 1.0


def test_defensive_two_point_returns_score():
    assert _aaa_points(_stats(), 20, _facts(aaa={"def_2pt": 1.0}), {"def_2pt": 2.0}) == 2.0


def _play(**fields: object) -> dict[str, object]:
    base: dict[str, object] = dict.fromkeys(streaming.PBP_COLUMNS)
    base |= {"season": 2026, "week": 1, "season_type": "REG", "special_teams_play": 0.0}
    base |= {"sack": 0.0, "touchdown": 0.0, "fumble": 0.0, "interception": 0.0}
    base |= {"yards_gained": 0.0, "defensive_two_point_conv": 0.0}
    return base | fields


def test_defense_play_facts_count_what_team_stats_lack():
    plays = [
        _play(posteam="BBB", defteam="AAA", sack=1.0, yards_gained=-7.0),
        _play(posteam="BBB", defteam="AAA", sack=1.0, yards_gained=-3.0),
        # BBB fumbles, AAA returns it for a touchdown
        _play(
            posteam="BBB",
            defteam="AAA",
            fumble=1.0,
            touchdown=1.0,
            td_team="AAA",
            fumbled_1_team="BBB",
            fumble_recovery_1_team="AAA",
        ),  # fmt: skip
        # BBB fumbles into the end zone and recovers its own ball: an offensive TD, not a return
        _play(
            posteam="BBB",
            defteam="AAA",
            fumble=1.0,
            touchdown=1.0,
            td_team="BBB",
            fumbled_1_team="BBB",
            fumble_recovery_1_team="BBB",
        ),  # fmt: skip
        # AAA punts, BBB muffs, AAA forces and recovers
        _play(
            posteam="AAA",
            defteam="BBB",
            special_teams_play=1.0,
            fumble=1.0,
            fumbled_1_team="BBB",
            fumble_recovery_1_team="AAA",
            forced_fumble_player_1_team="AAA",
        ),  # fmt: skip
        _play(posteam="BBB", defteam="AAA", defensive_two_point_conv=1.0),
        _play(posteam="BBB", defteam="AAA", season_type="POST", sack=1.0, yards_gained=-9.0),
    ]
    facts = streaming.defense_play_facts(pl.from_dicts(plays, infer_schema_length=None))
    aaa = facts.filter(pl.col("team") == "AAA").row(0, named=True)
    bbb = facts.filter(pl.col("team") == "BBB").row(0, named=True)
    assert bbb["sack_yards"] == -10.0
    assert aaa["fumble_return_tds"] == 1.0 and bbb["fumble_return_tds"] == 0.0
    assert aaa["st_fumble_recoveries"] == 1.0 and aaa["st_fumbles_forced"] == 1.0
    assert aaa["def_2pt"] == 1.0
    assert facts.height == 2


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


def test_a_team_the_schedules_call_oak_still_joins_the_team_stats_lv_rows():
    stats = _stats().with_columns(
        pl.when(pl.col("team") == "AAA").then(pl.lit("LV")).otherwise(pl.col("team")).alias("team"),
        pl.when(pl.col("opponent_team") == "AAA")
        .then(pl.lit("LV"))
        .otherwise(pl.col("opponent_team"))
        .alias("opponent_team"),
    )
    games = _games(10).with_columns(
        pl.when(pl.col("team") == "AAA").then(pl.lit("OAK")).otherwise(pl.col("team")).alias("team")
    )
    facts = _facts().with_columns(pl.col("team").replace({"AAA": "LV"}))
    out = defense_points_frame(stats, games, SCORING, "L", facts)
    assert sorted(out["team"].to_list()) == ["BBB", "LV"]
