"""Job keys across a clock bucket, per-account job caps, `?team=` checks, hidden docs routes."""

import threading
from collections.abc import Callable
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient

from fantasy import api_routes, data_api
from fantasy.api_jobs import MAX_ACTIVE_PER_OWNER, Busy, JobRunner


def _blocking_actions(monkeypatch: pytest.MonkeyPatch) -> tuple[threading.Event, list[str]]:
    gate, runs = threading.Event(), []

    def slow(league_key: str, *args: Any, **kwargs: Any) -> pl.DataFrame:
        runs.append(league_key)
        gate.wait(5)
        return pl.DataFrame({"kind": ["Lineup"], "text": ["x"]})

    monkeypatch.setattr(data_api, "actions", slow)
    return gate, runs


def _poll_until_ok(client: TestClient, path: str) -> dict[str, Any]:
    for _ in range(100):
        response = client.get(path)
        if response.status_code == 200:
            out: dict[str, Any] = response.json()
            return out
        threading.Event().wait(0.05)
    raise AssertionError("job never finished")


def test_a_job_polled_after_a_clock_bucket_change_is_the_same_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, runs = _blocking_actions(monkeypatch)
    buckets = iter(range(1, 100))  # the clock bucket moves on every request
    monkeypatch.setattr(
        api_routes.common, "data_version", lambda data_dir: f"100-5@{next(buckets)}"
    )
    assert client.get("/api/leagues/t/actions").status_code == 202
    assert client.get("/api/leagues/t/actions").status_code == 202
    gate.set()
    done = _poll_until_ok(client, "/api/leagues/t/actions")
    assert done["status"] == "ok"
    assert runs == ["t"]  # one simulation, not one per bucket
    assert len(client.app.state.runner._jobs) == 1  # type: ignore[attr-defined]


def test_a_rewritten_table_still_starts_a_new_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, runs = _blocking_actions(monkeypatch)
    gate.set()
    version = ["100-5@1"]
    monkeypatch.setattr(api_routes.common, "data_version", lambda data_dir: version[0])
    _poll_until_ok(client, "/api/leagues/t/actions")
    version[0] = "200-5@1"  # a stage rewrote a table
    _poll_until_ok(client, "/api/leagues/t/actions")
    assert runs == ["t", "t"]


def test_an_unknown_team_is_refused_without_a_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, runs = _blocking_actions(monkeypatch)
    for path in ("/api/leagues/t/actions?team=99", "/api/leagues/t/waivers?team=-4"):
        out = client.get(path).json()
        assert out["status"] == "error" and out["error"]["code"] == "invalid", path
    assert runs == [] and client.app.state.runner._jobs == {}  # type: ignore[attr-defined]


def test_a_roster_of_the_league_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, runs = _blocking_actions(monkeypatch)
    assert client.get("/api/leagues/t/actions?team=2").status_code == 202
    gate.set()
    assert _poll_until_ok(client, "/api/leagues/t/actions?team=2")["status"] == "ok"
    assert runs == ["t"]


def test_one_owner_cannot_take_every_slot() -> None:
    runner = JobRunner(max_workers=2)
    gate = threading.Event()
    for i in range(MAX_ACTIVE_PER_OWNER):
        runner.submit(("e", (i,), "v"), lambda: gate.wait(5), owner=7)
    with pytest.raises(Busy):
        runner.submit(("e", (99,), "v"), lambda: 1, owner=7)
    runner.submit(("e", (98,), "v"), lambda: 1, owner=8)  # someone else still gets a slot
    runner.submit(("e", (97,), "v"), lambda: 1)  # so does the admin, who has no owner
    assert runner.submit(("e", (0,), "v"), lambda: 1, owner=7).owner == 7  # same job: no new slot
    gate.set()
    runner.shutdown()


def test_the_owner_cap_frees_up_when_a_job_finishes() -> None:
    runner = JobRunner(max_workers=2)
    jobs = [
        runner.submit(("e", (i,), "v"), lambda: 1, owner=7) for i in range(MAX_ACTIVE_PER_OWNER)
    ]
    for job in jobs:
        job.future.result(5)
    assert runner.submit(("e", (99,), "v"), lambda: 2, owner=7).future.result(5) == 2
    runner.shutdown()


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_public_docs_routes_are_off(client: TestClient, path: str) -> None:
    response = client.get(path)  # 404, or the web app's shell when web/dist is built
    assert "swagger" not in response.text.lower() and "openapi" not in response.text[:200]


def test_the_schema_is_still_built_without_the_public_route(client: TestClient) -> None:
    schema: Callable[[], dict[str, Any]] = client.app.openapi  # type: ignore[attr-defined]
    assert "/api/leagues" in schema()["paths"]
