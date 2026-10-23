import polars as pl
import pytest

from fantasy.sim import schedule as s

SCHEMA = {
    "league_id": pl.String,
    "week": pl.Int64,
    "roster_id": pl.Int64,
    "matchup_id": pl.Int64,
    "points": pl.Float64,
}


def matchups(rows: list[tuple[int, int, int | None, float]]) -> pl.DataFrame:
    return pl.DataFrame([("L", *r) for r in rows], schema=SCHEMA, orient="row")


# week 1: 1 beats 2 (100-90), 3 beats 4 (80-70); week 2: 1 loses to 3 (60-95), 2 ties 4 (75-75)
GAMES = matchups(
    [
        (1, 1, 1, 100.0),
        (1, 2, 1, 90.0),
        (1, 3, 2, 80.0),
        (1, 4, 2, 70.0),
        (2, 1, 1, 60.0),
        (2, 3, 1, 95.0),
        (2, 2, 2, 75.0),
        (2, 4, 2, 75.0),
    ]  # fmt: skip
)


def test_pairings_one_row_per_matchup() -> None:
    p = s.pairings(GAMES)
    assert p.height == 4
    assert p.filter(pl.col("week") == 2).sort("roster_a").select("roster_a", "roster_b").rows() == [
        (1, 3),
        (2, 4),
    ]


def test_byes_without_a_matchup_id_are_not_paired() -> None:
    p = s.pairings(matchups([(1, 1, 1, 90.0), (1, 2, 1, 80.0), (1, 3, None, 70.0)]))
    assert p.height == 1


def test_standings_count_wins_losses_ties_and_points() -> None:
    table = s.standings(GAMES, through_week=2).sort("roster_id")
    rows = {r["roster_id"]: r for r in table.to_dicts()}
    assert (rows[1]["wins"], rows[1]["losses"], rows[1]["points_for"]) == (1, 1, 160.0)
    assert (rows[2]["wins"], rows[2]["losses"], rows[2]["ties"]) == (0, 1, 1)
    assert (rows[3]["wins"], rows[3]["losses"]) == (2, 0)
    assert rows[4]["ties"] == 1


def test_standings_ignore_weeks_after_the_cutoff() -> None:
    table = s.standings(GAMES, through_week=1)
    assert table["wins"].sum() == 2 and table["ties"].sum() == 0


def test_seed_order_is_wins_then_points_then_roster_id() -> None:
    table = pl.DataFrame(
        {
            "roster_id": [1, 2, 3, 4],
            "wins": [3, 3, 4, 3],
            "points_for": [500.0, 520.0, 400.0, 520.0],
        }
    )
    assert s.seed_order(table, 3) == [3, 2, 4]  # 2 and 4 tie on points, lower id first


def test_only_the_six_team_bracket_is_supported() -> None:
    assert s.bracket_rounds(6) == [[(3, 6), (4, 5)]]
    with pytest.raises(ValueError, match="6-team"):
        s.bracket_rounds(4)
