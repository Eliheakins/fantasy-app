import polars as pl
import pytest

from fantasy.stages import project as p

LEAGUE = "L1"
EXP_SCHEMA = {
    "league_id": pl.String,
    "gsis_id": pl.String,
    "season": pl.Int64,
    "week": pl.Int64,
    "position": pl.String,
    "team": pl.String,
    "exp_pts": pl.Float64,
    "points": pl.Float64,
}
GAME_SCHEMA = {
    "season": pl.Int64,
    "week": pl.Int64,
    "team": pl.String,
    "team_implied": pl.Float64,
    "game_type": pl.String,
}


TARGET_COLUMNS = ["league_id", "gsis_id", "season", "week", "position", "team"]


def exp_rows(rows: list[tuple[str, int, int, float]], team: str = "KC") -> pl.DataFrame:
    """rows: (player, season, week, expected points). All QBs."""
    data = [(LEAGUE, pid, s, w, "QB", team, x, x) for pid, s, w, x in rows]
    return pl.DataFrame(data, schema=EXP_SCHEMA, orient="row")


def games(rows: list[tuple[int, int, str, float | None]]) -> pl.DataFrame:
    data = [(s, w, team, implied, "REG") for s, w, team, implied in rows]
    return pl.DataFrame(data, schema=GAME_SCHEMA, orient="row")


def world(week3_exp: float = 10.0) -> pl.DataFrame:
    """A scores 10 in 2024 and 2025, B scores 0 in 2024 so the 2025 QB prior is 5."""
    rows = [("A", 2024, 1, 10.0), ("A", 2024, 2, 10.0), ("B", 2024, 1, 0.0), ("B", 2024, 2, 0.0)]
    rows += [("A", 2025, 1, 10.0), ("A", 2025, 2, 10.0), ("A", 2025, 3, week3_exp)]
    return exp_rows(rows)


def target(player: str, week: int, team: str = "KC") -> pl.DataFrame:
    return pl.DataFrame(
        [(LEAGUE, player, 2025, week, "QB", team)],
        schema={k: EXP_SCHEMA[k] for k in TARGET_COLUMNS},
        orient="row",
    )


NO_LINES = games([(2025, 3, "KC", None)])


def projection(exp: pl.DataFrame, tgt: pl.DataFrame, g: pl.DataFrame = NO_LINES) -> float:
    prior = p.position_prior(exp)
    form = p.build_form(exp, prior)
    return p.project_targets(tgt, form, prior, g)["projection"].item()


def test_projection_is_shrunk_recent_expected_points() -> None:
    # 4 games of 10 (n=4), prior 5, K=3: (4*10 + 3*5) / 7
    assert projection(world(), target("A", 3)) == pytest.approx(55 / 7)


def test_a_game_never_informs_its_own_projection() -> None:
    assert projection(world(week3_exp=100.0), target("A", 3)) == pytest.approx(55 / 7)


def test_debut_player_gets_the_position_prior() -> None:
    exp = world()
    prior = p.position_prior(exp)
    out = p.project_targets(target("C", 3), p.build_form(exp, prior), prior, NO_LINES)
    assert out["projection"].item() == pytest.approx(5.0)
    assert not out["has_history"].item()


def test_context_scales_by_implied_total_to_the_exponent() -> None:
    g = games([(2025, 3, "KC", 30.0), (2025, 3, "BUF", 10.0)])  # season average 20
    assert projection(world(), target("A", 3), g) == pytest.approx(55 / 7 * 1.5**0.5)


def test_future_targets_skip_bye_weeks() -> None:
    exp = world()
    form = p.build_form(exp, p.position_prior(exp))
    current = pl.DataFrame(
        {"gsis_id": ["A"], "team": ["KC"], "position": ["QB"]},
        schema={"gsis_id": pl.String, "team": pl.String, "position": pl.String},
    )
    none = pl.DataFrame(schema={"league_id": pl.String, "gsis_id": pl.String})
    plays = games([(2025, 4, "KC", None), (2025, 6, "KC", None), (2025, 5, "BUF", None)])
    out = p.future_targets(form, current, none, plays)
    assert sorted(out.filter(pl.col("gsis_id") == "A")["week"].to_list()) == [4, 6]
