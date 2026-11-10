import polars as pl

from fantasy._next_game import bye_week_of, next_games_by_team

SEASON = 2026
SCHEMA = {
    "season": pl.Int64, "week": pl.Int64, "gameday": pl.String, "gametime": pl.String,
    "away_team": pl.String, "home_team": pl.String, "away_score": pl.Int64, "home_score": pl.Int64,
}  # fmt: skip


def schedule(
    rows: list[tuple[int, str | None, str | None, str, str, int | None, int | None]],
) -> pl.DataFrame:
    return pl.DataFrame([(SEASON, *r) for r in rows], schema=SCHEMA, orient="row")


def test_names_the_opponent_and_kickoff_of_the_unplayed_game() -> None:
    games = schedule([(10, "2026-11-15", "13:00", "KC", "BUF", None, None)])

    home, away = (
        next_games_by_team(games, SEASON, 10)["BUF"],
        next_games_by_team(games, SEASON, 10)["KC"],
    )

    assert (home.short(), away.short()) == ("vs KC", "@ BUF")
    assert home.long() == "Week 10 vs KC, Sun 1:00 PM ET"


def test_skips_a_played_game_and_marks_a_bye() -> None:
    games = schedule([
        (10, "2026-11-12", "20:15", "KC", "BUF", 20, 17),
        (11, "2026-11-19", "20:15", "DEN", "BUF", None, None),
        (10, "2026-11-15", "13:00", "DEN", "MIA", None, None),
        (11, "2026-11-22", "13:00", "KC", "NYJ", None, None),
        (11, "2026-11-22", "16:00", "SEA", "LAR", None, None),
    ])  # fmt: skip

    nxt = next_games_by_team(games, SEASON, 10)

    assert nxt["BUF"].short() == "vs DEN"  # Thursday game is final
    assert nxt["NYJ"].short() == "Bye" and nxt["NYJ"].week == 10
    assert nxt["SEA"].long() == "Week 10 bye"


def test_has_no_entry_for_a_team_with_no_games_left() -> None:
    games = schedule([(9, "2026-11-08", "13:00", "KC", "BUF", 1, 0)])

    assert next_games_by_team(games, SEASON, 10) == {}


def test_finds_the_week_a_team_does_not_play() -> None:
    games = schedule([
        (4, "2026-10-04", "13:00", "KC", "BUF", 1, 0),
        (6, "2026-10-18", "13:00", "KC", "NYJ", 1, 0),
    ])  # fmt: skip

    assert bye_week_of(games, SEASON, "KC") == 5
    assert bye_week_of(games, SEASON, "DEN") is None
