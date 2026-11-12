from typing import Any

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
    raw: dict[str, dict[str, Any]] = {
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


# Anonymised copy of Sleeper's 6-team bracket shape (seeds 2 and 3 have byes).
BRACKET = [
    {"m": 1, "r": 1, "l": None, "w": None, "t1": 9, "t2": 8},
    {"m": 2, "r": 1, "l": None, "w": None, "t1": 6, "t2": 7},
    {"m": 3, "r": 2, "l": None, "w": None, "t1": 2, "t2": None, "t2_from": {"w": 1}},
    {"m": 4, "r": 2, "l": None, "w": None, "t1": 3, "t2": None, "t2_from": {"w": 2}},
    {"p": 5, "m": 5, "r": 2, "t1_from": {"l": 1}, "t2_from": {"l": 2}},
    {"p": 1, "m": 6, "r": 3, "t1_from": {"w": 3}, "t2_from": {"w": 4}},
    {"p": 3, "m": 7, "r": 3, "t1_from": {"l": 3}, "t2_from": {"l": 4}},
]


def test_bracket_parses_teams_byes_sources_and_places() -> None:
    df = s.bracket_frame("L1", "winners", BRACKET, 11)
    store.check_schema("playoff_brackets", df)
    rows = {r["m"]: r for r in df.to_dicts()}
    assert df.height == 7 and set(df["fetched_week"]) == {11} and set(df["bracket"]) == {"winners"}
    assert (rows[1]["t1"], rows[1]["t2"], rows[1]["t1_from_kind"]) == (9, 8, None)
    assert (rows[3]["t1"], rows[3]["t2"], rows[3]["t1_from_kind"]) == (2, None, None)
    assert (rows[3]["t2_from_kind"], rows[3]["t2_from_m"]) == ("w", 1)
    assert (rows[5]["t1_from_kind"], rows[5]["t1_from_m"], rows[5]["p"]) == ("l", 1, 5)
    assert [rows[m]["p"] for m in (1, 6, 7)] == [None, 1, 3]


def test_bracket_null_and_empty_give_no_rows() -> None:
    empty: list[Any] = [None, []]
    for raw in empty:
        df = s.bracket_frame("L1", "losers", raw, 3)
        store.check_schema("playoff_brackets", df)
        assert df.height == 0


def test_bracket_malformed_row_is_logged_not_raised(caplog: Any) -> None:
    df = s.bracket_frame("L1", "winners", [BRACKET[0], {"m": "x", "r": 1}, "junk"], 3)
    assert df.height == 0
    assert "bracket" in caplog.text
