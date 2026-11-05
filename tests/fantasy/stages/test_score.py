import polars as pl

from fantasy import store
from fantasy.stages import score as sc

SCHEDULE = pl.DataFrame(
    {
        "game_id": ["g1"],
        "season": [2026],
        "week": [7],
        "game_type": ["REG"],
        "gameday": ["2026-10-18"],
        "home_team": ["KC"],
        "away_team": ["BUF"],
        "home_score": [27],
        "away_score": [20],
        "spread_line": [3.0],  # home favored by 3
        "total_line": [50.0],
        "roof": ["outdoors"],
        "temp": [55.0],
        "wind": [8.0],
        "home_rest": [7.0],
        "away_rest": [7.0],
    }
)


def test_team_games_has_two_rows_with_spread_implied_totals() -> None:
    df = sc.team_games_frame(SCHEDULE)
    store.check_schema("team_games", df.select(*store.SCHEMAS["team_games"]))
    home = df.filter(pl.col("team") == "KC").to_dicts()[0]
    away = df.filter(pl.col("team") == "BUF").to_dicts()[0]
    assert (home["spread"], away["spread"]) == (3.0, -3.0)
    assert (home["team_implied"], home["opp_implied"]) == (26.5, 23.5)
    assert (away["team_implied"], away["opp_implied"]) == (23.5, 26.5)
    assert home["points_for"] == 27 and away["points_for"] == 20
    assert home["is_home"] and not away["is_home"]


def stat_row(**overrides: float | str) -> pl.DataFrame:
    schema = store.SCHEMAS["nfl_player_stats"]
    zero = {pl.Float64: 0.0, pl.Int64: 0}
    row = {c: zero.get(t) for c, t in schema.items()}  # type: ignore[call-overload]
    return pl.DataFrame([{**row, **overrides}], schema=schema)


def test_player_points_scores_per_league_and_attaches_context() -> None:
    stats = stat_row(
        player_id="00-1",
        position="WR",
        team="KC",
        season=2026,
        week=7,
        receptions=5.0,
        receiving_yards=60.0,
    )
    games = sc.team_games_frame(SCHEDULE)
    full = sc.player_points_frame(stats, games, {"rec": 1.0, "rec_yd": 0.1}, "L1")
    half = sc.player_points_frame(stats, games, {"rec": 0.5, "rec_yd": 0.1}, "L2")
    store.check_schema("player_points", full)
    assert full["points"].item() == 11.0 and half["points"].item() == 8.5
    assert full["team_implied"].item() == 26.5 and full["is_home"].item()
    assert full["league_id"].item() == "L1" and half["league_id"].item() == "L2"


def test_defensive_players_are_left_out() -> None:
    stats = stat_row(player_id="00-2", position="LB", team="KC", season=2026, week=7)
    out = sc.player_points_frame(stats, sc.team_games_frame(SCHEDULE), {"rec": 1.0}, "L1")
    assert out.is_empty()
