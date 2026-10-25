"""Viewing another team: every read treats the chosen roster as "my team"."""

import contextvars
import threading
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from test_api import client, store_dir, wait_ok  # noqa: F401  (fixtures)

from fantasy import _engine, api_routes, data_api
from fantasy._engine import viewed_team, viewing_team
from fantasy.api_jobs import JobRunner


def test_default_view_is_unchanged_and_the_override_resets(store_dir: Path) -> None:  # noqa: F811
    assert _engine._league("t")[1] == 1 and viewed_team() is None
    with viewing_team(2):
        assert _engine._league("t")[1] == 2 and viewed_team() == 2
    assert viewed_team() is None and _engine._league("t")[1] == 1


def test_same_team_as_me_gives_identical_results(store_dir: Path) -> None:  # noqa: F811
    calls = (
        lambda: data_api.lineup("t"),
        lambda: data_api.waivers("t"),
        lambda: data_api.roster("t", store_dir),
        lambda: data_api.season_odds("t", store_dir),
        lambda: data_api.schedule("t"),
        lambda: data_api.position_strength("t"),
    )
    base = [c().to_dicts() for c in calls]
    with viewing_team(1):
        assert [c().to_dicts() for c in calls] == base


def test_another_team_changes_roster_lineup_odds_flags_and_partners(
    store_dir: Path,  # noqa: F811
) -> None:
    mine_ids = set(data_api.lineup("t")["gsis_id"])
    with viewing_team(2):
        theirs = data_api.lineup("t")
        assert not mine_ids & set(theirs["gsis_id"])
        assert set(data_api.roster("t", store_dir)["full_name"]) == {"opp", "theirk"}
        odds = data_api.season_odds("t", store_dir)
        assert odds.filter(pl.col("is_me"))["roster_id"].to_list() == [2]
        partners = data_api.trade_partners("t")["roster_id"].to_list()
        assert 1 in partners and 2 not in partners
        assert data_api.seed_distribution("t").is_empty()  # the fixture has seeds for team 1 only
    back = data_api.season_odds("t", store_dir)
    assert back.filter(pl.col("is_me"))["roster_id"].to_list() == [1]


def test_teams_lists_every_team_with_me_marked(store_dir: Path) -> None:  # noqa: F811
    teams = data_api.teams("t", store_dir)
    assert teams["roster_id"].to_list() == [1, 2, 3, 4, 5, 6]
    assert teams.filter(pl.col("is_me"))["team_name"].to_list() == ["Mine"]
    with viewing_team(2):  # the list does not depend on the viewed team
        assert data_api.teams("t", store_dir).to_dicts() == teams.to_dicts()


def test_unknown_team_is_a_value_error(store_dir: Path) -> None:  # noqa: F811
    with viewing_team(99):
        with pytest.raises(ValueError, match="unknown team 99"):
            data_api.lineup("t")
        with pytest.raises(ValueError, match="unknown team 99"):
            data_api.roster("t", store_dir)


# --- API ----------------------------------------------------------------------------


def test_routes_follow_the_team_param_and_default_to_me(client: TestClient) -> None:  # noqa: F811
    default = client.get("/api/leagues/t/roster").json()["data"]
    same = client.get("/api/leagues/t/roster?team=1").json()["data"]
    other = client.get("/api/leagues/t/roster?team=2").json()["data"]
    assert default == same and default != other
    assert {r["full_name"] for r in other} == {"opp", "theirk"}
    odds = client.get("/api/leagues/t/season-odds?team=2").json()["data"]
    assert [r["roster_id"] for r in odds if r["is_me"]] == [2]


def test_teams_route(client: TestClient) -> None:  # noqa: F811
    out = client.get("/api/leagues/t/teams").json()
    assert out["status"] == "ok" and len(out["data"]) == 6
    assert [r["team_name"] for r in out["data"] if r["is_me"]] == ["Mine"]
    assert "record" in out["data"][0]


@pytest.mark.parametrize(
    "path", ["roster", "lineup", "schedule", "strength", "season-odds", "outlook", "trade-partners"]
)
def test_invalid_team_is_an_invalid_envelope(client: TestClient, path: str) -> None:  # noqa: F811
    out = client.get(f"/api/leagues/t/{path}?team=99").json()
    assert out["status"] == "error" and out["error"]["code"] == "invalid"


def test_invalid_team_on_a_job_and_a_trade(client: TestClient) -> None:  # noqa: F811
    out = wait_ok(client, lambda: client.get("/api/leagues/t/waivers?team=99"))
    assert out["error"]["code"] == "invalid"
    payload = {"partner_roster_id": 2, "give_ids": ["G_QB"], "get_ids": ["G_OPP"]}
    out = client.post("/api/leagues/t/trades/evaluate?team=99", json=payload).json()
    assert out["error"]["code"] == "invalid"


def test_trade_evaluate_is_from_the_viewed_team(client: TestClient) -> None:  # noqa: F811
    payload = {"partner_roster_id": 1, "give_ids": ["G_OPP"], "get_ids": ["G_RB"]}
    out = client.post("/api/leagues/t/trades/evaluate?team=2", json=payload).json()
    assert out["status"] == "ok"
    me = next(r for r in out["data"]["odds"] if r["side"] == "me")
    assert me["roster_id"] == 2


def test_job_keys_and_results_are_per_team(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = threading.Event()
    seen: list[int] = []

    def slow(league: str) -> pl.DataFrame:
        gate.wait(5)
        seen.append(_engine._league(league)[1])
        return pl.DataFrame({"kind": ["Lineup"], "text": [f"team {seen[-1]}"]})

    monkeypatch.setattr(data_api, "actions", slow)
    queries = ("?team=2", "", "?team=3")
    for q in queries:
        assert client.get(f"/api/leagues/t/actions{q}").status_code == 202
    gate.set()
    texts = [
        wait_ok(client, lambda q=q: client.get(f"/api/leagues/t/actions{q}"))["data"][0]["text"]
        for q in queries
    ]
    assert texts == ["team 2", "team 1", "team 3"]
    assert sorted(seen) == [1, 2, 3]


def test_override_is_set_in_the_worker_thread_and_reset_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = JobRunner(max_workers=1)  # one reused worker thread
    monkeypatch.setattr(api_routes, "known_league", lambda league: True)
    monkeypatch.setattr(api_routes, "data_version", lambda: "v")
    seen: list[int | None] = []
    api_routes.run_job(runner, "x", ("t",), lambda: seen.append(viewed_team()) or 1, team=7)
    for job in list(runner._jobs.values()):
        job.future.result(5)
    assert seen == [7] and viewed_team() is None
    after: list[int | None] = []
    runner.submit(("y", ("t",), "v"), lambda: after.append(viewed_team())).future.result(5)
    assert after == [None]  # the worker does not keep the last team
    runner.shutdown()


def test_threads_do_not_inherit_the_override_but_copied_contexts_do() -> None:
    seen: list[int | None] = []
    with viewing_team(5):
        t = threading.Thread(target=lambda: seen.append(viewed_team()))
        t.start()
        t.join()
        copied = contextvars.copy_context().run(viewed_team)
    assert seen == [None] and copied == 5 and viewed_team() is None
