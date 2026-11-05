from fantasy import store
from fantasy.stages import sync_sleeper as s

ROSTER = {
    "roster_id": 3,
    "owner_id": "u1",
    "players": ["10", "11", "12", "ARI"],
    "starters": ["10", "0", "ARI"],
    "reserve": ["12"],
    "settings": {"wins": 4, "losses": 2, "fpts": 700, "fpts_decimal": 25, "fpts_against": 650},
}


def test_rosters_skip_empty_slots_and_flag_starters_and_ir() -> None:
    df = s.rosters_frame("L1", [ROSTER])
    store.check_schema("rosters", df)
    by_id = {r["sleeper_id"]: r for r in df.to_dicts()}
    assert by_id["10"]["is_starter"] and by_id["ARI"]["is_starter"]
    assert not by_id["11"]["is_starter"]
    assert by_id["12"]["is_ir"]
    assert "0" not in by_id


def test_teams_use_team_name_and_combine_decimal_points() -> None:
    users = [{"user_id": "u1", "display_name": "Eli", "metadata": {"team_name": "Eli FC"}}]
    df = s.teams_frame("L1", [ROSTER], users, "u1")
    store.check_schema("league_teams", df)
    row = df.to_dicts()[0]
    assert row["team_name"] == "Eli FC" and row["is_me"]
    assert row["points_for"] == 700.25


def test_matchups_future_week_has_null_player_points() -> None:
    raw = [
        {
            "roster_id": 1,
            "matchup_id": 2,
            "points": 0.0,
            "starters": ["10", "0"],
            "players": ["10", "11"],
        },
        {"roster_id": 2, "matchup_id": 2, "points": 0.0, "starters": [], "players": []},
    ]
    teams, players = s.matchups_frames("L1", 9, raw)
    store.check_schema("matchups", teams)
    store.check_schema("matchup_players", players)
    assert players.height == 2
    assert players["points"].null_count() == 2
    assert players.filter(players["sleeper_id"] == "10")["is_starter"].item()


def test_matchups_played_week_carries_player_points() -> None:
    raw = [
        {
            "roster_id": 1,
            "matchup_id": 1,
            "points": 12.5,
            "starters": ["10"],
            "players": ["10"],
            "players_points": {"10": 12.5},
        }
    ]
    _, players = s.matchups_frames("L1", 6, raw)
    assert players["points"].to_list() == [12.5]


def test_transactions_one_row_per_player_action_with_bid() -> None:
    txs = [
        {
            "transaction_id": 99,
            "type": "waiver",
            "status": "complete",
            "created": 1,
            "adds": {"10": 3},
            "drops": {"11": 3},
            "settings": {"waiver_bid": 7},
        }
    ]
    df = s.transactions_frame("L1", 5, txs)
    store.check_schema("transactions", df)
    assert sorted(df["action"].to_list()) == ["add", "drop"]
    assert df["waiver_bid"].to_list() == [7, 7]


def test_players_keep_only_fantasy_positions_and_name_defenses() -> None:
    raw = {
        "1": {"position": "WR", "full_name": "A B", "team": "X", "fantasy_positions": ["WR"]},
        "2": {"position": "LB", "full_name": "C D"},
        "ARI": {"position": "DEF", "first_name": "Arizona", "last_name": "Cardinals"},
    }
    df = s.players_frame(raw)
    store.check_schema("sleeper_players", df)
    assert sorted(df["sleeper_id"].to_list()) == ["1", "ARI"]
    assert df.filter(df["sleeper_id"] == "ARI")["full_name"].item() == "Arizona Cardinals"


def test_empty_inputs_still_match_schema() -> None:
    for name in ("rosters", "matchups", "transactions", "trending"):
        store.check_schema(name, s._frame(name, []))
