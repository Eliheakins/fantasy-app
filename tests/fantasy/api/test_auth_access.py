import re
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from fantasy import api, store
from fantasy.auth import accounts, leagues, passwords

CSRF = {"X-Requested-With": "fantasy-app"}
GOOD = "a long enough password"
LEAGUE_ID = "L1"  # the league the shared test store holds, under the key "t"
FRIEND_SLEEPER_ID = "sleeper-friend"


@pytest.fixture(autouse=True)
def quick_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "COST_N", 2**10)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("LIVE_REFRESH", "off")
    monkeypatch.delenv("FANTASY_AUTH", raising=False)


def account_id(store_dir: Path, email: str) -> int:
    conn = accounts.connect(store_dir)
    try:
        return int(conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()[0])
    finally:
        conn.close()


def sign_in(store_dir: Path, email: str, *, admin: bool = False, grant: bool = False) -> TestClient:
    """A client signed in as `email`; `grant` gives that account the test league."""
    conn = accounts.connect(store_dir)
    if admin:
        accounts.create_admin(conn, email, GOOD)
    else:
        token = accounts.create_invite(conn, email, datetime.now(UTC))
        accounts.redeem_invite(conn, token, GOOD, datetime.now(UTC))
    if grant:
        conn.execute(
            "INSERT INTO account_leagues (account_id, league_id, added_at) VALUES (?, ?, ?)",
            (account_id_of(conn, email), LEAGUE_ID, accounts.stamp(datetime.now(UTC))),
        )
        conn.commit()
    conn.close()
    client = TestClient(
        api.create_app(data_dir=store_dir), base_url="http://localhost", headers=CSRF
    )
    login = client.post("/api/auth/login", json={"email": email, "password": GOOD})
    assert login.status_code == 200, login.text
    return client


def account_id_of(conn, email: str) -> int:  # noqa: ANN001
    return int(conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()[0])


def league_keys(client: TestClient) -> list[str]:
    response = client.get("/api/leagues")
    assert response.status_code == 200, response.text
    return [row["league_key"] for row in response.json()["data"]]


def league_get_paths(client: TestClient) -> list[str]:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    return sorted(
        re.sub(r"\{league\}", "t", re.sub(r"\{(?!league\})[^}]+\}", "x", path))
        for path, ops in paths.items()
        if "{league}" in path and "get" in ops
    )


def test_an_account_with_no_leagues_sees_none_and_gets_404_everywhere(store_dir: Path) -> None:
    friend = sign_in(store_dir, "friend@example.com")
    assert league_keys(friend) == []
    assert friend.get("/api/leagues/t/teams").status_code == 404
    assert friend.get("/api/leagues/nonexistent/teams").status_code == 404  # same answer


def test_the_admin_has_no_special_view_of_other_peoples_leagues(store_dir: Path) -> None:
    admin = sign_in(store_dir, "boss@example.com", admin=True)
    assert league_keys(admin) == []  # the test league is not in config.toml and not granted
    assert admin.get("/api/leagues/t/teams").status_code == 404


def test_a_granted_league_appears_and_works(store_dir: Path) -> None:
    friend = sign_in(store_dir, "friend@example.com", grant=True)
    assert league_keys(friend) == ["t"]
    assert friend.get("/api/leagues/t/teams").status_code == 200


def test_every_league_route_refuses_an_account_without_the_league(store_dir: Path) -> None:
    owner = sign_in(store_dir, "owner@example.com", grant=True)
    stranger = sign_in(store_dir, "stranger@example.com")
    paths = league_get_paths(owner)
    assert len(paths) >= 30  # the whole family, not a sample
    for path in paths:
        refused = stranger.get(path)
        assert refused.status_code == 404, path
        assert refused.json()["error"]["code"] == "no_data", path


def set_friend_as_a_roster(store_dir: Path, roster_id: int) -> None:
    teams = store.read_table("league_teams", "raw", store_dir)
    owner = pl.when(pl.col("roster_id") == roster_id).then(pl.lit(FRIEND_SLEEPER_ID))
    store.write_table(
        "league_teams",
        teams.with_columns(
            owner.otherwise(pl.col("owner_id")).alias("owner_id"),
            pl.lit(False).alias("is_me"),  # nobody is the owner here: this is a friend's league
        ),
        "raw",
        store_dir,
    )


def test_a_friends_default_team_is_the_roster_their_sleeper_id_owns(store_dir: Path) -> None:
    set_friend_as_a_roster(store_dir, roster_id=3)
    friend = sign_in(store_dir, "friend@example.com", grant=True)
    conn = accounts.connect(store_dir)
    accounts.set_sleeper_user(conn, account_id(store_dir, "friend@example.com"), FRIEND_SLEEPER_ID)
    conn.close()

    teams = {r["roster_id"]: r["is_me"] for r in friend.get("/api/leagues/t/teams").json()["data"]}
    assert [r for r, mine in teams.items() if mine] == [3]
    [row] = friend.get("/api/leagues").json()["data"]
    assert row["roster_id"] == 3
    default = friend.get("/api/leagues/t/roster").json()["data"]
    assert default == friend.get("/api/leagues/t/roster?team=3").json()["data"]


def test_a_friend_in_the_owners_league_gets_their_own_team_not_the_owners(
    store_dir: Path,
) -> None:
    teams = store.read_table("league_teams", "raw", store_dir)
    owners = teams.filter(pl.col("is_me"))["roster_id"].to_list()
    assert len(owners) == 1  # the shared store marks the owner's team, like a config.toml league
    friend_roster = next(r for r in teams["roster_id"].to_list() if r not in owners)
    store.write_table(
        "league_teams",
        teams.with_columns(
            pl.when(pl.col("roster_id") == friend_roster)
            .then(pl.lit(FRIEND_SLEEPER_ID))
            .otherwise(pl.col("owner_id"))
            .alias("owner_id")
        ),
        "raw",
        store_dir,
    )
    friend = sign_in(store_dir, "friend@example.com", grant=True)
    conn = accounts.connect(store_dir)
    accounts.set_sleeper_user(conn, account_id(store_dir, "friend@example.com"), FRIEND_SLEEPER_ID)
    conn.close()

    teams_seen = friend.get("/api/leagues/t/teams").json()["data"]
    assert [r["roster_id"] for r in teams_seen if r["is_me"]] == [friend_roster]
    [row] = friend.get("/api/leagues").json()["data"]
    assert row["roster_id"] == friend_roster


def test_the_team_an_account_picked_beats_the_one_its_sleeper_user_owns(store_dir: Path) -> None:
    set_friend_as_a_roster(store_dir, roster_id=3)
    friend = sign_in(store_dir, "friend@example.com", grant=True)
    conn = accounts.connect(store_dir)
    friend_id = account_id(store_dir, "friend@example.com")
    accounts.set_sleeper_user(conn, friend_id, FRIEND_SLEEPER_ID)
    leagues.set_team(conn, friend_id, LEAGUE_ID, 2)
    conn.close()

    teams = friend.get("/api/leagues/t/teams").json()["data"]
    assert [r["roster_id"] for r in teams if r["is_me"]] == [2]
    [row] = friend.get("/api/leagues").json()["data"]
    assert row["roster_id"] == 2
    assert (
        friend.get("/api/leagues/t/roster").json()
        == friend.get("/api/leagues/t/roster?team=2").json()
    )


def test_the_week_calendar_lists_only_the_accounts_leagues(store_dir: Path) -> None:
    friend = sign_in(store_dir, "friend@example.com")
    assert friend.get("/api/week-calendar").json()["data"]["waivers"] == []
    granted = sign_in(store_dir, "other@example.com", grant=True)
    waivers = granted.get("/api/week-calendar").json()["data"]["waivers"]
    assert [w["league_key"] for w in waivers] == ["t"]
