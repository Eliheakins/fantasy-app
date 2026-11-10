"""Viewing another team: every read treats the chosen roster as "my team"."""

import inspect
import threading
from functools import partial
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from test_api import wait_ok

from fantasy import _engine, data_api


def test_default_view_is_unchanged_and_the_team_argument_overrides_it(
    store_dir: Path,
) -> None:
    assert _engine._league("t", store_dir)[1] == 1
    assert _engine._league("t", store_dir, team=2)[1] == 2
    assert _engine._league("t", store_dir)[1] == 1


def test_same_team_as_me_gives_identical_results(store_dir: Path) -> None:
    calls = (
        data_api.lineup,
        data_api.waivers,
        data_api.roster,
        data_api.season_odds,
        data_api.schedule,
        data_api.position_strength,
    )
    base = [c("t", data_dir=store_dir).to_dicts() for c in calls]
    assert [c("t", data_dir=store_dir, team=1).to_dicts() for c in calls] == base


def test_another_team_changes_roster_lineup_odds_flags_and_partners(
    store_dir: Path,
) -> None:
    d = store_dir
    mine_ids = set(data_api.lineup("t", data_dir=d)["gsis_id"])
    theirs = data_api.lineup("t", data_dir=d, team=2)
    assert not mine_ids & set(theirs["gsis_id"])
    assert set(data_api.roster("t", d, team=2)["full_name"]) == {"opp", "theirk"}
    odds = data_api.season_odds("t", d, team=2)
    assert odds.filter(pl.col("is_me"))["roster_id"].to_list() == [2]
    partners = data_api.trade_partners("t", d, team=2)["roster_id"].to_list()
    assert 1 in partners and 2 not in partners
    assert data_api.seed_distribution("t", d, team=2).is_empty()  # seeds for team 1 only
    back = data_api.season_odds("t", d)
    assert back.filter(pl.col("is_me"))["roster_id"].to_list() == [1]


def test_teams_lists_every_team_with_me_marked(store_dir: Path) -> None:
    teams = data_api.teams("t", store_dir)
    assert teams["roster_id"].to_list() == [1, 2, 3, 4, 5, 6]
    assert teams.filter(pl.col("is_me"))["team_name"].to_list() == ["Mine"]


def test_unknown_team_is_a_value_error(store_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown team 99"):
        data_api.lineup("t", data_dir=store_dir, team=99)
    with pytest.raises(ValueError, match="unknown team 99"):
        data_api.roster("t", store_dir, team=99)


# --- API ----------------------------------------------------------------------------


def test_routes_follow_the_team_param_and_default_to_me(client: TestClient) -> None:
    default = client.get("/api/leagues/t/roster").json()["data"]
    same = client.get("/api/leagues/t/roster?team=1").json()["data"]
    other = client.get("/api/leagues/t/roster?team=2").json()["data"]
    assert default == same and default != other
    assert {r["full_name"] for r in other} == {"opp", "theirk"}
    odds = client.get("/api/leagues/t/season-odds?team=2").json()["data"]
    assert [r["roster_id"] for r in odds if r["is_me"]] == [2]


def test_teams_route(client: TestClient) -> None:
    out = client.get("/api/leagues/t/teams").json()
    assert out["status"] == "ok" and len(out["data"]) == 6
    assert [r["team_name"] for r in out["data"] if r["is_me"]] == ["Mine"]
    assert "record" in out["data"][0]


@pytest.mark.parametrize(
    "path", ["roster", "lineup", "schedule", "strength", "season-odds", "outlook", "trade-partners"]
)
def test_invalid_team_is_an_invalid_envelope(client: TestClient, path: str) -> None:
    out = client.get(f"/api/leagues/t/{path}?team=99").json()
    assert out["status"] == "error" and out["error"]["code"] == "invalid"


def test_invalid_team_on_a_job_and_a_trade(client: TestClient) -> None:
    out = wait_ok(client, lambda: client.get("/api/leagues/t/waivers?team=99"))
    assert out["error"]["code"] == "invalid"
    payload = {"partner_roster_id": 2, "give_ids": ["G_QB"], "get_ids": ["G_OPP"]}
    out = client.post("/api/leagues/t/trades/evaluate?team=99", json=payload).json()
    assert out["error"]["code"] == "invalid"


def test_trade_evaluate_is_from_the_viewed_team(client: TestClient) -> None:
    payload = {"partner_roster_id": 1, "give_ids": ["G_OPP"], "get_ids": ["G_RB"]}
    out = client.post("/api/leagues/t/trades/evaluate?team=2", json=payload).json()
    assert out["status"] == "ok"
    me = next(r for r in out["data"]["odds"] if r["side"] == "me")
    assert me["roster_id"] == 2


def test_job_keys_and_results_are_per_team(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = threading.Event()
    seen: list[int] = []

    def slow(league: str, *, data_dir: Path, team: int | None, **_: object) -> pl.DataFrame:
        gate.wait(5)
        seen.append(_engine._league(league, data_dir, team)[1])
        return pl.DataFrame({"kind": ["Lineup"], "text": [f"team {seen[-1]}"]})

    monkeypatch.setattr(data_api, "actions", slow)
    queries = ("?team=2", "", "?team=3")
    for q in queries:
        assert client.get(f"/api/leagues/t/actions{q}").status_code == 202
    gate.set()
    texts = [
        wait_ok(client, partial(client.get, f"/api/leagues/t/actions{q}"))["data"][0]["text"]
        for q in queries
    ]
    assert texts == ["team 2", "team 1", "team 3"]
    assert sorted(seen) == [1, 2, 3]


def test_jobs_run_for_the_viewed_roster_not_is_me(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, int] = {}

    def spy(name: str) -> None:
        real = getattr(data_api, name)

        def wrapper(*args: object, **kwargs: object) -> object:
            bound = inspect.signature(real).bind(*args, **kwargs)
            bound.apply_defaults()
            league, d, team = (bound.arguments[k] for k in ("league_key", "data_dir", "team"))
            seen[name] = _engine._league(league, d, team)[1]
            # the fixture league is too small for the real trade search
            return pl.DataFrame() if name == "find_trades" else real(*args, **kwargs)

        monkeypatch.setattr(data_api, name, wrapper)

    for name in ("win_probability", "actions", "find_trades"):
        spy(name)
    urls = (
        ("get", "/api/leagues/t/win-probability?week=3&team=2"),
        ("get", "/api/leagues/t/actions?team=2"),
        ("post", "/api/leagues/t/trades/find?team=2"),
    )
    for method, url in urls:
        out = wait_ok(client, partial(getattr(client, method), url))
        assert out["status"] == "ok", out
    assert seen == {"win_probability": 2, "actions": 2, "find_trades": 2}
    win = wait_ok(client, lambda: client.get("/api/leagues/t/win-probability?week=3&team=2"))
    mine = wait_ok(client, lambda: client.get("/api/leagues/t/win-probability?week=3"))
    best = lambda out: {r["gsis_id"] for r in out["data"]["lineups"]["expected_points"]}  # noqa: E731
    assert best(win) and not best(win) & best(mine)
