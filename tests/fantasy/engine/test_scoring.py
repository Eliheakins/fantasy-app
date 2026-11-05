import polars as pl
import pytest

from fantasy import store
from fantasy.scoring import check_keys, expected_points_expr, score_player_stats

SCHEMA = store.SCHEMAS["nfl_player_stats"]


def stat_line(**stats: float | str) -> pl.DataFrame:
    row: dict[str, float | str | int | None] = {}
    for column, dtype in SCHEMA.items():
        row[column] = 0.0 if dtype == pl.Float64 else (0 if dtype == pl.Int64 else None)
    row.update(stats)
    return pl.DataFrame([row], schema=SCHEMA)


def points(scoring: dict[str, float], **stats: float | str) -> float:
    return score_player_stats(stat_line(**stats), scoring)["points"].item()


PPR_1 = {"pass_yd": 0.04, "pass_td": 4, "pass_int": -1, "rush_yd": 0.1, "rush_td": 6}
PPR_1.update({"rec": 1.0, "rec_yd": 0.1, "rec_td": 6, "fum_lost": -2})


def test_quarterback_line() -> None:
    # 300 yds = 12, 2 TD = 8, 1 INT = -1, 20 rush yds = 2
    got = points(PPR_1, passing_yards=300, passing_tds=2, passing_interceptions=1, rushing_yards=20)
    assert got == 21.0


def test_receiver_ppr_levels_differ_only_by_receptions() -> None:
    line = {"receptions": 6, "receiving_yards": 80, "receiving_tds": 1}
    full = points({**PPR_1, "rec": 1.0}, **line)
    half = points({**PPR_1, "rec": 0.5}, **line)
    assert full == 6 + 8 + 6 and full - half == 3.0


def test_fumbles_lost_sum_all_three_kinds() -> None:
    got = points(PPR_1, sack_fumbles_lost=1, rushing_fumbles_lost=1, receiving_fumbles_lost=1)
    assert got == -6.0


def test_kicker_per_yard_and_extra_points() -> None:
    scoring = {"fgm_yds": 0.1, "fgmiss": -1, "xpm": 1, "xpmiss": -1}
    # 52 + 39 + 58 + 20 = 169 yards * 0.1 = 16.9, 3 PAT, 1 missed FG
    got = points(scoring, fg_made_list="52;39;58;20", pat_made=3, fg_missed=1)
    assert got == pytest.approx(16.9 + 3 - 1)


def test_expected_points_apply_league_weights_to_expected_stats() -> None:
    opp = pl.DataFrame(
        {
            "receptions_exp": [5.0],
            "rec_yards_gained_exp": [60.0],
            "rec_touchdown_exp": [0.5],
            "rush_yards_gained_exp": [None],
        },
        schema={
            "receptions_exp": pl.Float64,
            "rec_yards_gained_exp": pl.Float64,
            "rec_touchdown_exp": pl.Float64,
            "rush_yards_gained_exp": pl.Float64,
        },
    )
    base = {"rec_yd": 0.1, "rec_td": 6, "rush_yd": 0.1}
    full = opp.select(expected_points_expr({**base, "rec": 1.0}))
    half = opp.select(expected_points_expr({**base, "rec": 0.5}))
    assert full.item() == 5 + 6 + 3 and full.item() - half.item() == 2.5


def test_blocked_field_goal_counts_as_a_miss() -> None:
    assert points({"fgmiss": -2}, fg_missed=1, fg_blocked=1) == -4.0


def test_kicker_distance_buckets() -> None:
    scoring = {"fgm_30_39": 3, "fgm_50_59": 4, "fgm_60p": 5}
    got = points(scoring, fg_made_30_39=2, fg_made_50_59=1, fg_made_60_=1)
    assert got == 15.0


def test_no_kicks_means_zero_not_null() -> None:
    assert points({"fgm_yds": 0.1}) == 0.0


def test_unmapped_scoring_key_with_points_raises() -> None:
    with pytest.raises(ValueError, match="no mapping"):
        check_keys({"bonus_rec_te": 0.5})


def test_zero_weight_and_defense_keys_pass_the_check() -> None:
    check_keys({"bonus_rec_te": 0.0, "pts_allow_0": 10, "yds_allow_0_100": 5, "sack": 1})
