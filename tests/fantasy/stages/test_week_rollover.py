import polars as pl

from fantasy.config import REGULAR_SEASON_WEEKS
from fantasy.stages.week_rollover import advance_finished_week

SEASON = 2026


def schedule(rows: list[tuple[int, int | None, int | None]]) -> pl.DataFrame:
    return pl.DataFrame(
        [(SEASON, week, home, away) for week, home, away in rows],
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "home_score": pl.Int64,
            "away_score": pl.Int64,
        },
        orient="row",
    )


def leagues(week: int | None) -> pl.DataFrame:
    return pl.DataFrame({"current_week": [week]}, schema={"current_week": pl.Int64})


def test_advances_when_every_game_of_the_week_has_a_score() -> None:
    games = schedule([(9, 20, 10), (9, 3, 0), (10, None, None)])

    assert advance_finished_week(leagues(9), games, SEASON)["current_week"].to_list() == [10]


def test_stays_while_one_game_is_unplayed() -> None:
    games = schedule([(9, 20, 10), (9, None, None)])

    assert advance_finished_week(leagues(9), games, SEASON)["current_week"].to_list() == [9]


def test_stays_when_the_week_has_no_games() -> None:
    assert advance_finished_week(leagues(9), schedule([(8, 1, 0)]), SEASON)[
        "current_week"
    ].to_list() == [9]


def test_does_not_pass_the_last_week_and_keeps_a_null_week() -> None:
    games = schedule([(REGULAR_SEASON_WEEKS, 1, 0)])

    assert advance_finished_week(leagues(REGULAR_SEASON_WEEKS), games, SEASON)[
        "current_week"
    ].to_list() == [REGULAR_SEASON_WEEKS]
    assert advance_finished_week(leagues(None), games, SEASON)["current_week"].to_list() == [None]
