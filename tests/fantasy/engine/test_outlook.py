import polars as pl
import pytest

from fantasy.sim.outlook import Context, apply_outlook, effects_dict, return_factors
from fantasy.stages import outlook as stage

FIRST, SECOND = 0.8, 0.9


def test_a_healthy_returner_gets_the_first_then_second_game_ratio_then_full() -> None:
    out = return_factors([1.0, 1.0, 1.0], True, False, FIRST, SECOND)
    assert out == pytest.approx([FIRST, SECOND, 1.0])


def test_a_player_who_returned_last_week_is_in_his_second_game_back() -> None:
    assert return_factors([1.0, 1.0], False, True, FIRST, SECOND) == pytest.approx([SECOND, 1.0])


def test_a_player_who_was_playing_is_not_ramped() -> None:
    assert return_factors([1.0, 1.0], False, False, FIRST, SECOND) == [1.0, 1.0]


def test_the_ramp_follows_the_injury_curve() -> None:
    # out now, back in game 1 with probability .5 and in game 2 otherwise
    out = return_factors([0.0, 0.5, 1.0], True, False, FIRST, SECOND)
    assert out[0] == 1.0  # no points either way, the factor is irrelevant
    assert out[1] == pytest.approx(FIRST)  # if he plays game 1, it is his first back
    assert out[2] == pytest.approx(1 - 0.5 * (1 - FIRST) - 0.5 * (1 - SECOND))


def _effects() -> dict[tuple[str, str], float]:
    return {
        ("WR", "first_back_injury"): FIRST,
        ("WR", "second_back_injury"): SECOND,
        ("WR", "first_back_other"): 0.6,
        ("WR", "second_back_other"): 0.8,
        ("WR", "vac_target"): 3.0,
        ("WR", "vac_carry"): 0.0,
        ("QB", "vac_target"): 0.0,
        ("QB", "vac_carry"): 0.0,
    }


def _projections() -> pl.DataFrame:
    rows = []
    for g, pos, p in (
        ("star", "WR", 0.0),
        ("mate", "WR", 1.0),
        ("qb", "QB", 1.0),
        ("other", "WR", 1.0),
    ):
        team = "B" if g == "other" else "A"
        for week in (6, 7, 8):
            rows.append((g, week, pos, team, 10.0 * p, p))
    return pl.DataFrame(
        rows,
        schema=["gsis_id", "week", "position", "team", "projection", "play_prob"],
        orient="row",
    )


def test_teammates_out_lift_receivers_on_that_team_only_and_not_the_absent_player() -> None:
    context = Context(
        {}, {}, {"star": ("A", 0.3, 0.0), "mate": ("A", 0.1, 0.0), "qb": ("A", 0.0, 0.0)}
    )
    out = apply_outlook(_projections(), context, _effects(), current_week=7)
    got = {r["gsis_id"]: r for r in out.filter(pl.col("week") == 7).iter_rows(named=True)}
    assert got["mate"]["vacancy_points"] == pytest.approx(3.0 * 0.3)
    assert got["mate"]["projection"] == pytest.approx(10.0 + 0.9)
    assert got["qb"]["vacancy_points"] == 0.0  # quarterbacks do not absorb targets
    assert got["other"]["vacancy_points"] == 0.0  # another team
    assert got["star"]["projection"] == 0.0  # absent: no points, no self-boost
    assert out.filter(pl.col("week") == 6)["vacancy_points"].sum() == 0.0  # past weeks untouched


def test_a_returning_player_is_ramped_by_the_kind_of_absence() -> None:
    frame = _projections().filter(pl.col("gsis_id") == "mate")
    injured = Context({"mate": (1, True)}, {}, {})
    benched = Context({"mate": (1, False)}, {}, {})
    a = apply_outlook(frame, injured, _effects(), 7).filter(pl.col("week") == 7)
    b = apply_outlook(frame, benched, _effects(), 7).filter(pl.col("week") == 7)
    assert a["projection"][0] == pytest.approx(10.0 * FIRST)
    assert b["projection"][0] == pytest.approx(10.0 * 0.6)


def _panel() -> pl.DataFrame:
    rows = []
    for i in range(40):
        rows.append(
            {
                "position": "WR",
                "first_back": i < 10,
                "second_back": False,
                "injured_gap": i < 5,
                "prev_injured": False,
                "vac_target": 0.2 if i >= 20 else 0.0,
                "vac_carry": 0.0,
                "projection": 10.0,
                "points": 8.0 if i < 5 else 6.0 if i < 10 else (13.0 if i >= 20 else 10.0),
            }
        )
    return pl.DataFrame(rows).with_columns((pl.col("points") - pl.col("projection")).alias("miss"))


def test_estimate_recovers_return_ratios_and_the_vacancy_slope() -> None:
    table = stage.estimate(pl.concat([_panel()] * 100))  # enough rows that the ridge is light
    effects = effects_dict(table)
    assert effects[("WR", "first_back_injury")] == pytest.approx(0.8)
    assert effects[("WR", "first_back_other")] == pytest.approx(0.6)
    assert effects[("WR", "vac_target")] == pytest.approx(15.0, rel=0.05)  # 3 points per 0.2
    assert ("QB", "first_back_injury") not in effects  # no games: no row, not a ratio of 1.0


def test_live_context_finds_returners_and_tells_injury_from_benching() -> None:
    stats = pl.DataFrame(
        [
            ("hurt", 1, "T", 0.2, 5.0),
            ("hurt", 2, "T", 0.2, 5.0),
            ("hurt", 5, "T", 0.2, 5.0),
            ("sat", 1, "T", 0.1, 3.0),
            ("sat", 5, "T", 0.1, 3.0),
            ("fine", 1, "T", 0.1, 3.0),
            ("fine", 2, "T", 0.1, 3.0),
            ("fine", 3, "T", 0.1, 3.0),
            ("fine", 4, "T", 0.1, 3.0),
            ("fine", 5, "T", 0.1, 3.0),
        ],
        schema=["player_id", "week", "team", "target_share", "carries"],
        orient="row",
    ).with_columns(pl.lit("REG").alias("season_type"), pl.lit(2026).alias("season"))
    team_stats = pl.DataFrame(
        {"team": ["T"] * 5, "season": [2026] * 5, "week": [1, 2, 3, 4, 5], "carries": [20.0] * 5}
    ).with_columns(pl.lit("REG").alias("season_type"))
    games = pl.DataFrame(
        {"team": ["T"] * 5, "season": [2026] * 5, "week": [1, 2, 3, 4, 5], "game_type": ["REG"] * 5}
    )
    injuries = pl.DataFrame(
        {"gsis_id": ["hurt"], "season": [2026], "week": [3], "game_type": ["REG"]}
    )
    context = stage.live_context(stats, team_stats, games, injuries, 2026, current_week=6)
    assert context.missed == {}  # all three played the last game
    assert context.after_return == {"hurt": True, "sat": False}
    assert "fine" not in context.after_return
    assert context.usage["hurt"][1] > 0
