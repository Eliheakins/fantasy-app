from pathlib import Path
from typing import Any

import pytest
from auth_fixture import GOOD, isolate_auth, make_client, sign_in
from fastapi.testclient import TestClient

from fantasy import refresh_queue
from fantasy.auth import accounts, my_leagues
from fantasy.auth.ratelimit import FailureLimiter
from fantasy.config import load_config
from fantasy.sources.sleeper import SleeperError

STANDARD = {"num_teams": 10, "playoff_teams": 6, "playoff_week_start": 15}
CHOPPED = {"num_teams": 16, "playoff_teams": None, "playoff_week_start": 0}  # weekly eliminations


class FakeSleeper:
    """Just enough of Sleeper's API: users by name, a user's leagues, a league's rosters and
    users."""

    def __init__(self) -> None:
        self.users: dict[str, Any] = {
            "FriendUser": {"user_id": "u-friend", "display_name": "Friend"},
            "OtherUser": {"user_id": "u-other", "display_name": "Other"},
        }
        self.leagues: dict[str, list[dict[str, Any]]] = {
            "u-friend": [
                {
                    "league_id": "111",
                    "name": "Friends League",
                    "total_rosters": 10,
                    "settings": STANDARD,
                },
                {"league_id": "222", "name": "Second", "total_rosters": 12, "settings": STANDARD},
                {"league_id": "333", "name": "Third", "total_rosters": 8, "settings": STANDARD},
                {"league_id": "444", "name": "Chopped", "total_rosters": 16, "settings": CHOPPED},
                {
                    "league_id": "555",
                    "name": "Bonus",
                    "total_rosters": 10,
                    "settings": STANDARD,
                    "scoring_settings": {"rec": 1.0, "bonus_rec_te": 0.5},
                    "roster_positions": ["QB", "RB", "WR", "BN"],
                },
                {
                    "league_id": "666",
                    "name": "Odd lineup",
                    "total_rosters": 10,
                    "settings": STANDARD,
                    "scoring_settings": {"rec": 1.0},
                    "roster_positions": ["QB", "RB", "WRRB_FLEX", "BN"],
                },
            ],
            "u-other": [
                {
                    "league_id": "111",
                    "name": "Friends League",
                    "total_rosters": 10,
                    "settings": STANDARD,
                }
            ],
        }
        self.rosters: dict[str, list[dict[str, Any]]] = {
            "111": [
                {"roster_id": 1, "owner_id": "u-friend"},
                {"roster_id": 2, "owner_id": "u-other"},
            ],
            "222": [{"roster_id": 1, "owner_id": "u-friend"}],
            "333": [{"roster_id": 1, "owner_id": "u-friend"}],
            "444": [{"roster_id": 1, "owner_id": "u-friend"}],
            "555": [{"roster_id": 1, "owner_id": "u-friend"}],
            "666": [{"roster_id": 1, "owner_id": "u-friend"}],
        }
        self.down = False
        self.calls: list[str] = []

    def __call__(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(path)
        if self.down:
            raise SleeperError("Sleeper request failed")
        parts = path.strip("/").split("/")
        if parts[0] == "user" and len(parts) == 2:
            return self.users.get(parts[1])  # Sleeper answers null for a name it does not know
        if parts[0] == "user" and parts[2] == "leagues":
            assert parts[3:] == ["nfl", str(load_config().season)], path
            return self.leagues.get(parts[1], [])
        if parts[0] == "league" and parts[2] == "rosters":
            return self.rosters.get(parts[1], [])
        if parts[0] == "league" and parts[2] == "users":
            owners = {r["owner_id"] for r in self.rosters.get(parts[1], [])}
            return [
                {**user, "metadata": {"team_name": f"{user['display_name']} FC"}}
                for user in self.users.values()
                if user["user_id"] in owners
            ]
        raise AssertionError(f"unexpected Sleeper call {path}")


@pytest.fixture(autouse=True)
def quick_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_auth(monkeypatch)
    monkeypatch.setattr(my_leagues, "lookup_limiter", FailureLimiter(limit=10, window_s=60.0))


@pytest.fixture
def sleeper(monkeypatch: pytest.MonkeyPatch) -> FakeSleeper:
    fake = FakeSleeper()
    monkeypatch.setattr(my_leagues, "fetch", fake)
    return fake


@pytest.fixture
def friend(store_dir: Path, sleeper: FakeSleeper) -> TestClient:
    return sign_in(store_dir, "friend@example.com")


def lookup(client: TestClient, username: str = "FriendUser") -> Any:
    return client.post("/api/me/sleeper/lookup", json={"username": username})


def add(
    client: TestClient, league_id: str, username: str = "FriendUser", roster_id: int = 1
) -> Any:
    body = {"username": username, "league_id": league_id, "roster_id": roster_id}
    return client.post("/api/me/leagues", json=body)


def test_lookup_lists_the_users_current_leagues_and_which_are_already_added(
    friend: TestClient,
) -> None:
    assert add(friend, "111").status_code == 200
    data = lookup(friend).json()["data"]
    assert (data["display_name"], data["user_id"]) == ("Friend", "u-friend")
    assert {lg["league_id"]: lg["added"] for lg in data["leagues"]} == {
        "111": True,
        "222": False,
        "333": False,
        "444": False,
        "555": False,
        "666": False,
    }
    assert data["leagues"][0]["num_teams"] == 10


def test_lookup_of_an_unknown_name_says_so(friend: TestClient) -> None:
    response = lookup(friend, "NoSuchUser")
    assert response.status_code == 404
    assert "No Sleeper user" in response.json()["error"]["message"]


def test_lookup_refuses_a_name_that_could_not_be_one(
    friend: TestClient, sleeper: FakeSleeper
) -> None:
    for bad in ("", "a b", "../etc", "x" * 60, "name?x=1"):
        assert lookup(friend, bad).status_code in {400, 422}, bad
    assert sleeper.calls == []  # nothing odd ever reaches Sleeper


def test_lookup_reports_a_sleeper_outage_without_a_stack_trace(
    friend: TestClient, sleeper: FakeSleeper
) -> None:
    sleeper.down = True
    response = lookup(friend)
    assert response.status_code == 502
    assert "Sleeper" in response.json()["error"]["message"]


def test_lookups_are_limited_so_sleeper_is_not_hammered(friend: TestClient) -> None:
    for _ in range(10):
        assert lookup(friend).status_code == 200
    blocked = lookup(friend)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "busy"


def test_adding_a_league_queues_it_links_the_sleeper_user_and_asks_for_a_refresh(
    friend: TestClient, store_dir: Path
) -> None:
    response = add(friend, "111")
    assert response.status_code == 200
    row = response.json()["data"]
    assert (row["league_id"], row["league_key"], row["status"]) == ("111", "sl-111", "queued")
    assert refresh_queue.status(store_dir)["state"] == "queued"
    conn = accounts.connect(store_dir)
    assert conn.execute("SELECT sleeper_user_id FROM accounts").fetchone()[0] == "u-friend"
    conn.close()
    assert [r["league_id"] for r in friend.get("/api/me/leagues").json()["data"]] == ["111"]


def test_a_league_that_is_not_the_users_is_refused(friend: TestClient) -> None:
    response = add(friend, "999")
    assert response.status_code == 404
    assert "not one of" in response.json()["error"]["message"]


def test_a_league_where_no_team_is_the_users_is_refused(
    friend: TestClient, sleeper: FakeSleeper
) -> None:
    sleeper.rosters["111"] = [{"roster_id": 2, "owner_id": "u-other"}]
    response = add(friend, "111")
    assert response.status_code == 409
    assert "no team" in response.json()["error"]["message"].lower()


def test_an_account_stays_linked_to_the_sleeper_user_it_first_used(friend: TestClient) -> None:
    assert add(friend, "111").status_code == 200
    response = add(friend, "111", username="OtherUser")
    assert response.status_code == 409
    assert "already linked" in response.json()["error"]["message"]


def test_the_third_league_is_refused_with_the_reason(friend: TestClient) -> None:
    assert add(friend, "111").status_code == 200
    assert add(friend, "222").status_code == 200
    response = add(friend, "333")
    assert response.status_code == 409
    assert "up to 2" in response.json()["error"]["message"]


def test_adding_the_same_league_twice_is_fine(friend: TestClient) -> None:
    assert add(friend, "111").status_code == 200
    assert add(friend, "111").status_code == 200
    assert len(friend.get("/api/me/leagues").json()["data"]) == 1


def test_a_league_mate_adding_the_same_league_shares_it(
    store_dir: Path, sleeper: FakeSleeper
) -> None:
    first = sign_in(store_dir, "a@example.com")
    second = sign_in(store_dir, "b@example.com")
    assert add(first, "111").status_code == 200
    assert add(second, "111", username="OtherUser", roster_id=2).status_code == 200
    conn = accounts.connect(store_dir)
    assert conn.execute("SELECT COUNT(*) FROM league_registry").fetchone()[0] == 1
    conn.close()


def test_removing_a_league_frees_the_place_and_404s_for_one_that_is_not_yours(
    friend: TestClient,
) -> None:
    add(friend, "111")
    add(friend, "222")
    assert friend.delete("/api/me/leagues/111").status_code == 200
    assert friend.delete("/api/me/leagues/111").status_code == 404
    assert add(friend, "333").status_code == 200


def test_signed_out_visitors_get_nothing(store_dir: Path, sleeper: FakeSleeper) -> None:
    conn = accounts.connect(store_dir)
    accounts.create_admin(conn, "boss@example.com", GOOD)
    conn.close()
    client = make_client(store_dir)
    assert lookup(client).status_code == 401
    assert add(client, "111").status_code == 401
    assert client.get("/api/me/leagues").status_code == 401
    assert sleeper.calls == []


def test_lookup_marks_the_leagues_the_app_cannot_model_with_the_reason(friend: TestClient) -> None:
    leagues = {lg["league_id"]: lg for lg in lookup(friend).json()["data"]["leagues"]}
    assert leagues["111"]["problem"] is None
    assert "no playoff" in leagues["444"]["problem"]


def test_a_league_the_app_cannot_model_cannot_be_added(friend: TestClient, store_dir: Path) -> None:
    response = add(friend, "444")
    assert response.status_code == 409
    assert "no playoff" in response.json()["error"]["message"]
    assert friend.get("/api/me/leagues").json()["data"] == []
    assert refresh_queue.status(store_dir)["state"] == "idle"  # and no refresh was asked for


def test_adding_a_league_keeps_the_team_picked_as_yours(friend: TestClient) -> None:
    assert add(friend, "111", roster_id=2).json()["data"]["roster_id"] == 2
    [row] = friend.get("/api/me/leagues").json()["data"]
    assert row["roster_id"] == 2


def test_adding_needs_a_team_and_one_that_is_in_the_league(friend: TestClient) -> None:
    missing = friend.post("/api/me/leagues", json={"username": "FriendUser", "league_id": "111"})
    assert missing.status_code == 422
    response = add(friend, "111", roster_id=9)
    assert response.status_code == 409
    assert "not in that league" in response.json()["error"]["message"]
    assert friend.get("/api/me/leagues").json()["data"] == []


def test_the_teams_to_pick_from_carry_their_owners(friend: TestClient) -> None:
    teams = friend.get("/api/me/sleeper/leagues/111/teams").json()["data"]
    assert teams == [
        {"roster_id": 1, "team_name": "Friend FC", "owner_id": "u-friend", "owner_name": "Friend"},
        {"roster_id": 2, "team_name": "Other FC", "owner_id": "u-other", "owner_name": "Other"},
    ]
    assert friend.get("/api/me/sleeper/leagues/abc/teams").status_code == 422


def test_an_unowned_team_is_named_by_its_number(friend: TestClient, sleeper: FakeSleeper) -> None:
    sleeper.rosters["222"].append({"roster_id": 2, "owner_id": None})
    teams = friend.get("/api/me/sleeper/leagues/222/teams").json()["data"]
    assert teams[1] == {"roster_id": 2, "team_name": "Team 2", "owner_id": None, "owner_name": None}


def test_the_team_in_an_added_league_can_be_changed(friend: TestClient) -> None:
    add(friend, "111")
    response = friend.put("/api/me/leagues/111/team", json={"roster_id": 2})
    assert response.json()["data"] == {"league_id": "111", "roster_id": 2}
    [row] = friend.get("/api/me/leagues").json()["data"]
    assert row["roster_id"] == 2


def test_changing_the_team_needs_your_league_and_a_team_in_it(friend: TestClient) -> None:
    add(friend, "111")
    assert friend.put("/api/me/leagues/222/team", json={"roster_id": 1}).status_code == 404
    refused = friend.put("/api/me/leagues/111/team", json={"roster_id": 9})
    assert refused.status_code == 409
    assert friend.get("/api/me/leagues").json()["data"][0]["roster_id"] == 1


@pytest.mark.parametrize(("league_id", "words"), [("555", "bonus_rec_te"), ("666", "WRRB_FLEX")])
def test_a_league_with_scoring_or_a_slot_the_app_cannot_handle_is_refused_at_add_time(
    friend: TestClient, store_dir: Path, league_id: str, words: str
) -> None:
    flagged = {lg["league_id"]: lg for lg in lookup(friend).json()["data"]["leagues"]}
    assert words in flagged[league_id]["problem"]
    response = add(friend, league_id)
    assert response.status_code == 409
    assert words in response.json()["error"]["message"]
    assert friend.get("/api/me/leagues").json()["data"] == []
    assert refresh_queue.status(store_dir)["state"] == "idle"


def owner_in_sleeper(sleeper: FakeSleeper) -> str:
    """Put the app owner's Sleeper user and one of the config.toml leagues into the fake."""
    cfg = load_config()
    config_league = next(iter(cfg.leagues.values()))
    sleeper.users["OwnerName"] = {"user_id": cfg.user_id, "display_name": "Owner"}
    sleeper.leagues[cfg.user_id] = [
        {"league_id": config_league, "name": "Mine", "total_rosters": 10, "settings": STANDARD}
    ]
    sleeper.rosters[config_league] = [{"roster_id": 1, "owner_id": cfg.user_id}]
    return config_league


def test_a_friend_cannot_add_a_league_from_config_toml(
    friend: TestClient, sleeper: FakeSleeper
) -> None:
    config_league = owner_in_sleeper(sleeper)
    sleeper.leagues["u-friend"].append(
        {"league_id": config_league, "name": "Mine", "total_rosters": 10, "settings": STANDARD}
    )
    response = add(friend, config_league)
    assert response.status_code == 409
    assert "owner" in response.json()["error"]["message"]
    assert friend.get("/api/me/leagues").json()["data"] == []


def test_a_friend_cannot_claim_the_owners_sleeper_identity(
    friend: TestClient, sleeper: FakeSleeper
) -> None:
    config_league = owner_in_sleeper(sleeper)
    sleeper.leagues[load_config().user_id].append(
        {"league_id": "777", "name": "Owner side league", "total_rosters": 10, "settings": STANDARD}
    )
    sleeper.rosters["777"] = [{"roster_id": 1, "owner_id": load_config().user_id}]
    response = add(friend, "777", username="OwnerName")
    assert response.status_code == 409
    assert "owner" in response.json()["error"]["message"]
    assert config_league not in {
        lg["league_id"] for lg in friend.get("/api/me/leagues").json()["data"]
    }


def test_the_admin_may_add_the_owners_league(store_dir: Path, sleeper: FakeSleeper) -> None:
    config_league = owner_in_sleeper(sleeper)
    admin = sign_in(store_dir, "boss@example.com", admin=True)
    response = add(admin, config_league, username="OwnerName")
    assert response.status_code == 200, response.text


def test_adding_removing_and_changing_teams_share_the_lookup_limit(friend: TestClient) -> None:
    add(friend, "111")
    for _ in range(9):  # the add above was the first of ten
        assert lookup(friend).status_code == 200
    assert add(friend, "111").status_code == 429
    assert friend.delete("/api/me/leagues/111").status_code == 429
    assert friend.put("/api/me/leagues/111/team", json={"roster_id": 2}).status_code == 429
    assert len(friend.get("/api/me/leagues").json()["data"]) == 1  # nothing was removed


def test_posting_a_league_that_is_already_registered_queues_no_refresh(
    store_dir: Path, sleeper: FakeSleeper
) -> None:
    first = sign_in(store_dir, "a@example.com")
    second = sign_in(store_dir, "b@example.com")
    assert add(first, "111").status_code == 200
    assert refresh_queue.consume(store_dir) == ["league added: 111"]
    assert add(first, "111").status_code == 200  # a repeat
    assert add(second, "111", username="OtherUser", roster_id=2).status_code == 200  # a league-mate
    assert refresh_queue.status(store_dir)["state"] == "idle"
