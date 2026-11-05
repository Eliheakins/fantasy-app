"""Team grades: the rank-to-letter rule and the per-position table."""

import polars as pl
import pytest
from test_odds import WEEKS, toy_league

from fantasy.sim.depth import position_depth
from fantasy.sim.grades import DEPTH_WEIGHT, STARTER_WEIGHT, grade_for_rank, team_grades

POSITIONS = ("QB", "RB", "WR", "TE")


def test_ten_team_league_gets_two_teams_per_letter() -> None:
    assert "".join(grade_for_rank(r, 10) for r in range(1, 11)) == "AABBCCDDFF"


def test_two_team_league_gets_an_a_and_a_c() -> None:
    assert [grade_for_rank(1, 2), grade_for_rank(2, 2)] == ["A", "C"]


def test_a_one_team_league_is_an_a() -> None:
    assert grade_for_rank(1, 1) == "A"


@pytest.mark.parametrize("teams", [5, 7, 12, 14])
def test_grades_never_improve_as_rank_worsens_and_span_a_to_f(teams: int) -> None:
    letters = [grade_for_rank(r, teams) for r in range(1, teams + 1)]
    assert letters == sorted(letters, key=lambda g: "ABCDF".index(g))
    assert letters[0] == "A" and letters[-1] == "F"


def _strength(values: dict[int, dict[str, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [(r, p, v) for r, by in values.items() for p, v in by.items()],
        schema=["roster_id", "position", "vor_per_week"],
        orient="row",
    )


def _depth(values: dict[int, dict[str, float]]) -> pl.DataFrame:
    return _strength(values).rename({"vor_per_week": "depth_per_week"})


def _grade(strength: dict, depth: dict | None = None, n: int | None = None, **weights: float):
    depth = depth or {r: dict.fromkeys(by, 0.0) for r, by in strength.items()}
    return team_grades(_strength(strength), _depth(depth), _teams(n or len(strength)), **weights)


def _teams(n: int, me: int = 1) -> pl.DataFrame:
    ids = list(range(1, n + 1))
    return pl.DataFrame(
        {"roster_id": ids, "team_name": [f"T{r}" for r in ids], "is_me": [r == me for r in ids]}
    )


def _rank(table: pl.DataFrame, roster_id: int, position: str) -> int:
    return table.filter((pl.col("roster_id") == roster_id) & (pl.col("position") == position))[
        "rank"
    ][0]


def test_weights_sum_to_one_and_favour_starters() -> None:
    assert STARTER_WEIGHT + DEPTH_WEIGHT == pytest.approx(1.0) and STARTER_WEIGHT > DEPTH_WEIGHT


def test_better_starter_beats_better_bench_at_75_25_and_loses_at_25_75() -> None:
    starters = {1: {"RB": 10.0}, 2: {"RB": 8.0}}  # team 1 has the starter
    bench = {1: {"RB": 0.0}, 2: {"RB": 2.0}}  # team 2 has the bench
    default = _grade(starters, bench)
    flipped = _grade(starters, bench, starter_weight=0.25, depth_weight=0.75)
    assert _rank(default, 1, "RB") == 1 and _rank(default, 2, "RB") == 2
    assert _rank(flipped, 2, "RB") == 1 and _rank(flipped, 1, "RB") == 2


def test_two_team_toy_league_ranks_and_grades_each_position_and_overall() -> None:
    table = _grade(
        {
            1: {"QB": 5.0, "RB": 1.0, "WR": 1.0, "TE": 1.0},  # overall 8
            2: {"QB": 1.0, "RB": 4.0, "WR": 2.0, "TE": 0.0},  # overall 7
        }
    )
    cell = {(r["roster_id"], r["position"]): (r["rank"], r["grade"]) for r in table.to_dicts()}
    assert cell[1, "QB"] == (1, "A") and cell[2, "QB"] == (2, "C")
    assert cell[1, "RB"] == (2, "C") and cell[2, "RB"] == (1, "A")
    assert cell[1, "overall"] == (1, "A") and cell[2, "overall"] == (2, "C")
    assert table.height == 10


def test_overall_adds_scaled_depth_to_starters() -> None:
    table = _grade(
        {1: {"QB": 4.0, "RB": 4.0}, 2: {"QB": 5.0, "RB": 4.0}},
        {1: {"QB": 3.0, "RB": 3.0}, 2: {"QB": 0.0, "RB": 0.0}},
    )
    one = table.filter((pl.col("roster_id") == 1) & (pl.col("position") == "overall"))["score"][0]
    assert one == pytest.approx(8.0 + 6.0 * DEPTH_WEIGHT / STARTER_WEIGHT)


def test_zero_spread_gives_everyone_the_same_score_not_nan() -> None:
    table = _grade({r: {"QB": 3.0} for r in range(1, 5)})
    qb = table.filter(pl.col("position") == "QB")
    assert qb["score"].to_list() == [0.0] * 4 and set(qb["rank"]) == {1}


def test_tied_teams_share_a_rank_and_a_grade() -> None:
    values = {r: {"QB": 1.0} for r in range(1, 9)} | {9: {"QB": 0.0}, 10: {"QB": 0.0}}
    table = _grade(values).filter(pl.col("position") == "QB")
    top, bottom = table.filter(pl.col("roster_id") <= 8), table.filter(pl.col("roster_id") >= 9)
    assert set(top["rank"]) == {1} and set(top["grade"]) == {"A"}
    assert set(bottom["rank"]) == {9} and set(bottom["grade"]) == {"F"}


def test_is_me_comes_from_the_teams_table() -> None:
    table = team_grades(
        _strength({1: {"QB": 1.0}, 2: {"QB": 2.0}}),
        _depth({1: {"QB": 0.0}, 2: {"QB": 0.0}}),
        _teams(2, me=2),
    )
    assert table.filter(pl.col("is_me"))["roster_id"].unique().to_list() == [2]


def _with_bench() -> "object":
    """Toy league where team 1 has two extra backup RBs and a starter RB on bye for 5 weeks."""
    data = toy_league()
    extra = [("t1_rb3", "RB", 10.0), ("t1_rb4", "RB", 9.0)]
    rosters = pl.concat(
        [
            data.rosters,
            pl.DataFrame(
                [(1, g, p) for g, p, _ in extra], schema=data.rosters.schema, orient="row"
            ),
        ]
    )
    proj = data.projections.filter(~((pl.col("gsis_id") == "t1_rb1") & (pl.col("week") <= 5)))
    rows = [(g, w, v) for g, _, v in extra for w in WEEKS]
    proj = pl.concat([proj, pl.DataFrame(rows, schema=proj.schema, orient="row")])
    from dataclasses import replace

    return replace(data, rosters=rosters, projections=proj)


def test_depth_is_zero_without_a_bench_and_positive_behind_a_bye_prone_starter() -> None:
    depth = position_depth(_with_bench())  # type: ignore[arg-type]
    cell = {(r["roster_id"], r["position"]): r["depth_per_week"] for r in depth.to_dicts()}
    assert cell[2, "QB"] == 0.0 and cell[2, "RB"] == 0.0 and cell[1, "QB"] == 0.0
    assert cell[1, "RB"] > 0.0
