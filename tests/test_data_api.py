from pathlib import Path

import polars as pl

from fantasy import data_api, store
from fantasy.stages import sync_sleeper as s

LEAGUE = {
    "league_id": "L1",
    "name": "Test League",
    "season": "2026",
    "status": "in_season",
    "settings": {"leg": 7, "num_teams": 10},
    "roster_positions": ["QB", "RB", "SUPER_FLEX", "BN"],
    "scoring_settings": {"rec": 0.5, "pass_td": 4, "pass_int": -2},
}
ROSTERS = [
    {
        "roster_id": 1,
        "owner_id": "me",
        "players": ["3", "2", "1"],
        "starters": ["1", "2"],
        "settings": {"wins": 3, "losses": 3},
    },
    {"roster_id": 2, "owner_id": "other", "players": ["9"], "starters": [], "settings": {}},
]
USERS = [{"user_id": "me", "display_name": "Eli", "metadata": {"team_name": "Eli FC"}}]
PLAYERS = {
    "1": {"position": "RB", "full_name": "Runner One", "team": "KC", "status": "Active"},
    "2": {"position": "QB", "full_name": "Passer Two", "team": "BUF", "status": "Active"},
    "3": {"position": "QB", "full_name": "Backup Three", "team": "CHI", "status": "Active"},
    "9": {"position": "WR", "full_name": "Other Nine", "team": "MIA", "status": "Active"},
}


def write_sample(tmp_path: Path) -> None:
    tables = {
        "leagues": s.league_frame("test", LEAGUE),
        "league_teams": s.teams_frame("L1", ROSTERS, USERS, "me"),
        "rosters": s.rosters_frame("L1", ROSTERS),
        "sleeper_players": s.players_frame(PLAYERS),
    }
    for name, df in tables.items():
        store.write_table(name, df, area="raw", data_dir=tmp_path)


def test_scoring_labels() -> None:
    scoring = {"rec": 1.0, "pass_td": 4, "pass_int": -1}
    labels = data_api.scoring_labels(scoring, ["QB", "SUPER_FLEX"])
    assert labels == ["1 PPR", "4-pt pass TD", "-1 per INT", "Superflex"]
    assert "Superflex" not in data_api.scoring_labels({"rec": 0.5}, ["QB", "FLEX"])


def test_leagues_has_my_team_and_scoring(tmp_path: Path) -> None:
    write_sample(tmp_path)
    row = data_api.leagues(tmp_path).to_dicts()[0]
    assert row["team_name"] == "Eli FC" and row["wins"] == 3
    assert row["scoring_labels"] == "0.5 PPR, 4-pt pass TD, -2 per INT, Superflex"


def test_roster_puts_starters_first_then_position_order(tmp_path: Path) -> None:
    write_sample(tmp_path)
    df = data_api.roster("test", tmp_path)
    assert df["full_name"].to_list() == ["Passer Two", "Runner One", "Backup Three"]
    assert df["is_starter"].to_list() == [True, True, False]


def test_season_odds_marks_my_team_and_sorts_by_title_odds(tmp_path: Path) -> None:
    write_sample(tmp_path)
    rows = [
        ("L1", "Eli FC", 1, 7, 100, 0.6, 0.1, 0.05, 7.0),
        ("L1", "Other", 2, 7, 100, 0.4, 0.2, 0.30, 6.0),
    ]
    odds = pl.DataFrame(rows, schema=store.SCHEMAS["sim_season"], orient="row")
    store.write_table("sim_season", odds, data_dir=tmp_path)
    out = data_api.season_odds("test", tmp_path)
    assert out["team_name"].to_list() == ["Other", "Eli FC"]
    assert out["is_me"].to_list() == [False, True]
    assert data_api.season_odds("nope", tmp_path).is_empty()


def test_odds_history_returns_saved_runs_for_the_league(tmp_path: Path) -> None:
    write_sample(tmp_path)
    run = ("L1", "Eli FC", "2026-10-23T00:00:00+00:00", 1, 7, 100, 0.6, 0.1, 0.05, 7.0)
    history = pl.DataFrame([run], schema=store.SCHEMAS["sim_season_history"], orient="row")
    store.write_table("sim_season_history", history, area="archive", data_dir=tmp_path)
    out = data_api.odds_history("test", tmp_path)
    assert out.height == 1 and out["p_title"].item() == 0.05
    assert data_api.odds_history("test", tmp_path / "empty").is_empty()


def test_unmatched_uses_the_crosswalk_not_the_sleeper_file_id(tmp_path: Path) -> None:
    write_sample(tmp_path)
    id_map = pl.DataFrame(
        {
            "sleeper_id": ["1", "2", "3", "9"],
            "gsis_id": ["G1", "G2", None, "G9"],
            "nfl_team": ["KC", "BUF", "CHI", "MIA"],
            "match_method": ["ffplayerids", "ffplayerids", "none", "ffplayerids"],
        }
    )
    store.write_table("id_map", id_map, data_dir=tmp_path)
    assert data_api.unmatched(tmp_path)["sleeper_id"].to_list() == ["3"]


def test_missing_tables_return_empty_frames_not_errors(tmp_path: Path) -> None:
    assert data_api.leagues(tmp_path).is_empty()
    assert data_api.roster("test", tmp_path).is_empty()
    assert data_api.unmatched(tmp_path).is_empty()
    assert data_api.season_odds("test").columns[:2] == ["roster_id", "team_name"]


def test_missing_layers_names_the_projection_layers_whose_stage_has_not_run(tmp_path):
    assert "injury model" in data_api.missing_layers(tmp_path)
    store.write_table(
        "outlook_effects",
        pl.DataFrame(schema=store.SCHEMAS["outlook_effects"]),
        data_dir=tmp_path,
    )
    missing = data_api.missing_layers(tmp_path)
    assert "outlook" not in missing and "injury model" in missing
