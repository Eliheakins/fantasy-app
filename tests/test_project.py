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


def test_longer_horizon_ignores_recent_games_and_context() -> None:
    exp = world()
    prior = p.position_prior(exp)
    form = p.build_form(exp, prior)
    g = games([(2025, 3, "KC", 30.0), (2025, 3, "BUF", 10.0)])
    five = p.project_targets(target("A", 3), form, prior, g, horizon=5)
    # only the two 2024 games count: (2*10 + 3*5) / 5 = 7, and the context is neutral
    assert five["projection"].item() == pytest.approx(7.0)
    assert five["context"].item() == 1.0


def test_debut_player_gets_the_position_prior() -> None:
    exp = world()
    prior = p.position_prior(exp)
    out = p.project_targets(target("C", 3), p.build_form(exp, prior), prior, NO_LINES)
    assert out["projection"].item() == pytest.approx(5.0)
    assert not out["has_history"].item()


def test_context_scales_by_implied_total_to_the_exponent() -> None:
    g = games([(2025, 3, "KC", 30.0), (2025, 3, "BUF", 10.0)])  # season average 20
    assert projection(world(), target("A", 3), g) == pytest.approx(55 / 7 * 1.5**0.25)


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


def test_future_targets_drop_a_player_with_no_current_team() -> None:
    exp = world()
    form = p.build_form(exp, p.position_prior(exp))
    current = pl.DataFrame(
        {"gsis_id": ["A"], "team": [None], "position": ["QB"]},
        schema={"gsis_id": pl.String, "team": pl.String, "position": pl.String},
    )
    none = pl.DataFrame(schema={"league_id": pl.String, "gsis_id": pl.String})
    plays = games([(2025, 4, "KC", None)])
    assert p.future_targets(form, current, none, plays).filter(pl.col("gsis_id") == "A").is_empty()


def test_a_horizon_shift_across_a_season_boundary_uses_the_previous_seasons_games() -> None:
    exp = world()  # A has 2024 weeks 1-2 and 2025 weeks 1-3
    prior = p.position_prior(exp)
    form = p.build_form(exp, prior)
    out = p.project_targets(target("A", 3), form, prior, NO_LINES, horizon=5)
    # five weeks ahead of week 3 is before the season began: the latest allowed game is 2024 week 2
    assert (out["as_of_season"].item(), out["as_of_week"].item()) == (2024, 2)
    nearer = p.project_targets(target("A", 6), form, prior, NO_LINES, horizon=5)
    assert (nearer["as_of_season"].item(), nearer["as_of_week"].item()) == (2025, 1)  # origin: wk 2


def test_week_index_is_monotone_across_seasons() -> None:
    frame = pl.DataFrame({"season": [2024, 2024, 2025], "week": [1, 22, 1]})
    idx = frame.select(p.week_index())["season"].to_list()
    assert idx == sorted(idx) and len(set(idx)) == 3


def _opp(players: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        {"player_id": players, "season": [2025] * len(players), "week": [1] * len(players)}
    )


def test_expected_points_with_no_scored_row_are_dropped_not_scored_as_zero(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(p, "expected_points_expr", lambda scoring: pl.lit(5.0))
    opp = _opp(["A", "B"]).with_columns(position=pl.lit("WR"), posteam=pl.lit("KC"))
    points = pl.DataFrame(
        {"league_id": ["L1"], "gsis_id": ["A"], "season": [2025], "week": [1], "points": [9.0]}
    )
    leagues = pl.DataFrame({"league_id": ["L1"], "scoring_settings": ["{}"]})
    monkeypatch.setattr(p, "MAX_UNSCORED_SHARE", 0.6)
    out = p.expected_frame(opp, points, leagues)
    assert out["gsis_id"].to_list() == ["A"]
    monkeypatch.setattr(p, "MAX_UNSCORED_SHARE", 0.1)
    with pytest.raises(ValueError, match="no points"):
        p.expected_frame(opp, points, leagues)


def test_rostered_players_with_no_history_on_any_team_get_the_position_prior() -> None:
    exp = world()
    form = p.build_form(exp, p.position_prior(exp))
    current = pl.DataFrame({"gsis_id": ["A", "R"], "team": ["KC", "KC"], "position": ["QB", "QB"]})
    rostered = pl.DataFrame({"league_id": ["L2"], "gsis_id": ["R"]})  # a rival's rookie
    plays = games([(2025, 4, "KC", None)])
    out = p.future_targets(form, current, rostered, plays)
    assert out.filter(pl.col("gsis_id") == "R")["league_id"].to_list() == ["L2"]
    left_out = p.unprojected_rostered(rostered, current, out.filter(pl.col("gsis_id") == "A"))
    assert left_out["len"].to_list() == [1]
