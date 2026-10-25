import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows
from test_data_api_characterization import _engine_store

from fantasy import _engine, api, api_routes, data_api, store
from fantasy.api_jobs import Busy, JobRunner

ROOT = Path(__file__).resolve().parent.parent
CSRF_HEADER = {"X-Requested-With": "fantasy-app"}
LEAGUE_ROWS = [
    {"league_key": "t", "league_id": "L1", "name": "Test", "roster_id": 1},
]


@pytest.fixture
def store_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _engine_store(tmp_path, monkeypatch)
    original = data_api.leagues
    monkeypatch.setattr(data_api, "leagues", lambda *a, **k: original(tmp_path))
    write_rows(
        tmp_path,
        "sim_season",
        [
            {"league_id": "L1", "roster_id": 1, "team_name": "Mine", "p_title": 0.5},
            {"league_id": "L1", "roster_id": 2, "team_name": "Theirs", "p_title": 0.1},
        ],
    )
    write_rows(tmp_path, "sim_seeds", [{"league_id": "L1", "roster_id": 1, "seed": 1, "p": 1.0}])
    history = [
        {"league_id": "L1", "roster_id": r, "team_name": n, "run_at": "2026-09-01"}
        for r, n in ((1, "Mine"), (2, "Theirs"))
    ]
    frame = pl.DataFrame(history, schema=store.SCHEMAS["sim_season_history"])
    store.write_table("sim_season_history", frame, "archive", tmp_path)
    write_rows(
        tmp_path,
        "streaming_projection",
        [
            {"league_id": "L1", "kind": "K", "unit": "G_FREEK", "team": "KC", "week": 3}
            | {"projection": 6.0},
        ],
    )
    _engine._clear_league_cache()
    return tmp_path


@pytest.fixture
def client(store_dir: Path) -> Iterator[TestClient]:
    with TestClient(api.create_app(), base_url="http://localhost", headers=CSRF_HEADER) as c:
        yield c


def body(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    out = response.json()
    assert set(out) >= {"status", "data", "error"}
    return out


def columns(rows: list[dict[str, Any]]) -> set[str]:
    assert rows, "expected at least one row"
    return set(rows[0])


# --- envelope helpers -----------------------------------------------------------------


def test_rows_turns_nan_into_none_and_keeps_other_values() -> None:
    frame = pl.DataFrame({"a": [1.0, float("nan")], "b": ["x", None], "c": [[1], [2]]})
    assert api.rows(frame) == [
        {"a": 1.0, "b": "x", "c": [1]},
        {"a": None, "b": None, "c": [2]},
    ]


def test_clean_replaces_nan_and_inf_anywhere_in_nested_data() -> None:
    nested = {"a": [float("nan"), {"b": float("inf")}], "c": 1.5}
    assert api.clean(nested) == {"a": [None, {"b": None}], "c": 1.5}


# --- status, leagues, caching ----------------------------------------------------------


def test_status_reports_freshness_layers_and_version_in_one_call(client: TestClient) -> None:
    out = body(client.get("/api/status"))
    assert out["status"] == "ok" and out["error"] is None
    data = out["data"]
    assert set(data) == {"freshness", "missing_layers", "simulation_behind_inputs", "data_version"}
    assert "injury model" in data["missing_layers"]
    assert {r["source"] for r in data["freshness"]} >= {"Sleeper"}


def test_leagues_has_record_fallback_and_trade_deadline(client: TestClient) -> None:
    rows = body(client.get("/api/leagues"))["data"]
    assert [r["league_key"] for r in rows] == ["t"]
    assert rows[0]["record"] == "no record yet" and rows[0]["trade_deadline"] is None
    assert rows[0]["team_name"] == "Mine"


def test_data_version_reads_data_dir_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _engine.data_version() != "0-0"  # the real data folder, or "0-0" on a fresh clone
    empty = tmp_path / "empty"
    monkeypatch.setattr(_engine.store, "DATA_DIR", empty)
    assert _engine.data_version() == "0-0"
    (empty / "raw").mkdir(parents=True)
    (empty / "raw" / "a.parquet").write_bytes(b"12345")
    first = _engine.data_version()
    assert first.endswith("-5")
    (empty / "raw" / "a.parquet").write_bytes(b"123456")
    assert _engine.data_version() != first


def count_builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from fantasy.stages import simulate

    calls: list[str] = []
    real = simulate.load_league_data

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append("build")
        return real(*args, **kwargs)

    monkeypatch.setattr(simulate, "load_league_data", counting)
    return calls


def test_league_build_is_cached_until_a_parquet_file_changes(
    client: TestClient, store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = count_builds(monkeypatch)
    body(client.get("/api/leagues/t/schedule"))
    body(client.get("/api/leagues/t/strength"))
    assert len(calls) == 1
    path = store_dir / "raw" / "rosters.parquet"
    write_rows(store_dir, "rosters", [{"league_id": "L1", "roster_id": 1, "sleeper_id": "qb"}])
    stamp = path.stat().st_mtime + 5  # a coarse filesystem clock must not hide the rewrite
    os.utime(path, (stamp, stamp))
    body(client.get("/api/leagues/t/strength"))
    assert len(calls) == 2


def test_refresh_calls_sleeper_then_clears_the_caches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = count_builds(monkeypatch)
    monkeypatch.setattr(data_api, "refresh_live", lambda: 7)
    body(client.get("/api/leagues/t/strength"))
    out = body(client.post("/api/live/refresh"))
    assert out["data"] == {"player_rows": 7}
    body(client.get("/api/leagues/t/strength"))
    assert len(calls) == 2


# --- jobs -----------------------------------------------------------------------------


def test_job_runner_is_single_flight_and_returns_the_result_when_done() -> None:
    runner = JobRunner(max_workers=2)
    gate, runs = threading.Event(), []

    def work() -> int:
        runs.append(1)
        gate.wait(5)
        return 42

    first = runner.submit(("e", (), "v1"), work)
    second = runner.submit(("e", (), "v1"), work)
    assert first is second and not first.future.done()
    gate.set()
    assert first.future.result(5) == 42 and len(runs) == 1
    assert runner.submit(("e", (), "v1"), work).future.result() == 42 and len(runs) == 1
    assert runner.submit(("e", (), "v2"), lambda: 1).future.result(5) == 1  # new data, new job
    runner.shutdown()


def wait_until(check: Callable[[], bool]) -> None:
    for _ in range(100):
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_a_job_route_goes_running_then_ok_and_runs_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, runs = threading.Event(), []

    def slow(league_key: str, *args: Any, **kwargs: Any) -> pl.DataFrame:
        runs.append(league_key)
        gate.wait(5)
        return pl.DataFrame({"kind": ["Lineup"], "text": ["x"]})

    monkeypatch.setattr(data_api, "actions", slow)
    first = client.get("/api/leagues/t/actions")
    assert first.status_code == 202
    assert first.json()["status"] == "running" and first.json()["started_at"]
    assert client.get("/api/leagues/t/actions").status_code == 202
    gate.set()
    wait_until(lambda: client.get("/api/leagues/t/actions").status_code == 200)
    done = client.get("/api/leagues/t/actions").json()
    assert done["status"] == "ok" and done["data"] == [
        {"kind": "Lineup", "text": "x", "delta_points": None, "share_better": None}
    ]
    assert runs == ["t"]


def test_a_failed_job_reports_the_error_and_can_be_retried(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()

    def broken(*args: Any, **kwargs: Any) -> pl.DataFrame:
        gate.wait(5)
        raise ValueError("the trade deadline (week 2) has passed")

    monkeypatch.setattr(data_api, "find_trades", broken)
    assert client.post("/api/leagues/t/trades/find").status_code == 202
    gate.set()

    seen: list[dict[str, Any]] = []

    def failed() -> bool:
        r = client.post("/api/leagues/t/trades/find")
        if r.status_code == 200:
            seen.append(r.json())
        return r.status_code == 200

    wait_until(failed)
    assert seen[0]["status"] == "error"
    assert seen[0]["error"] == {
        "code": "invalid",
        "message": "the trade deadline (week 2) has passed",
    }
    assert client.post("/api/leagues/t/trades/find").status_code in (200, 202)  # retried


# --- hosts and static files -----------------------------------------------------------


def test_unknown_host_header_is_rejected(store_dir: Path) -> None:
    with TestClient(api.create_app(), base_url="http://evil.example") as c:
        assert c.get("/api/status").status_code == 400


def test_hosts_from_the_environment_are_allowed(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_ALLOWED_HOSTS", "box.tail1234.ts.net, other.local")
    with TestClient(api.create_app(), base_url="http://box.tail1234.ts.net") as c:
        assert c.get("/api/status").status_code == 200
    with TestClient(api.create_app(), base_url="http://127.0.0.1") as c:
        assert c.get("/api/status").status_code == 200


def test_static_files_absent_is_a_404_and_present_is_served(
    store_dir: Path, tmp_path: Path
) -> None:
    with TestClient(api.create_app(web_dist=tmp_path / "nope"), base_url="http://localhost") as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/status").status_code == 200
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>hi</html>")
    with TestClient(api.create_app(web_dist=dist), base_url="http://localhost") as c:
        assert "hi" in c.get("/").text
        assert c.get("/api/status").status_code == 200


# --- errors ---------------------------------------------------------------------------


def test_unknown_league_is_an_error_envelope(client: TestClient) -> None:
    out = body(client.get("/api/leagues/zzz/lineup"))
    assert out["status"] == "error" and out["data"] is None
    assert out["error"]["code"] == "invalid" and "zzz" in out["error"]["message"]


def test_missing_data_is_the_no_data_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: Any, **kwargs: Any) -> pl.DataFrame:
        raise FileNotFoundError("no table")

    monkeypatch.setattr(data_api, "lineup", missing)
    out = body(client.get("/api/leagues/t/lineup"))
    assert out["status"] == "error" and out["error"]["code"] == "no_data"


def test_trade_after_the_deadline_is_an_error_with_the_message(
    client: TestClient, store_dir: Path
) -> None:
    write_rows(store_dir, "leagues", [dict(_league_row(store_dir), trade_deadline=2)])
    payload = {"partner_roster_id": 2, "give_ids": ["G_RB"], "get_ids": ["G_OPP"]}
    out = body(client.post("/api/leagues/t/trades/evaluate", json=payload))
    assert out["status"] == "error" and "deadline" in out["error"]["message"]


def _league_row(store_dir: Path) -> dict[str, Any]:
    return pl.read_parquet(store_dir / "raw" / "leagues.parquet").row(0, named=True)


# --- route smoke tests: envelope and column set ----------------------------------------

LINEUP = {
    "slot", "gsis_id", "full_name", "position", "projection", "p10", "p90", "starting_now",
    "recommended", "injury", "injury_note", "locked", "actual", "game", "change",
}  # fmt: skip
ROWS = {
    "/api/leagues/t/roster": {
        "sleeper_id", "full_name", "position", "team", "injury_status", "is_starter", "is_ir",
    },
    "/api/leagues/t/season-odds": {
        "roster_id", "team_name", "p_playoffs", "p_bye", "p_title", "exp_wins", "is_me",
    },
    "/api/leagues/t/seeds": {"seed", "p"},
    "/api/leagues/t/odds-history": {"run_at", "team_name", "roster_id", "p_playoffs", "p_title"},
    "/api/leagues/t/streamers?kind=K": {
        "unit", "name", "team", "is_mine", "this_week", "next_three",
    },
    "/api/leagues/t/lineup?week=3": LINEUP,
    "/api/leagues/t/schedule": {"week", "opponent", "my_points", "their_points", "win_chance"},
    "/api/leagues/t/strength": {"position", "vor_per_week", "rank", "teams"},
    "/api/leagues/t/team-grades": {
        "roster_id", "team_name", "is_me", "position", "vor_per_week", "depth_per_week", "score",
        "rank", "grade",
    },
    "/api/leagues/t/live-score": {"side", "team_name", "points", "projected_final"},
    "/api/leagues/t/trade-partners": {"roster_id", "team_name"},
    "/api/leagues/t/trade-assets": {"gsis_id", "full_name", "position", "ros_points", "label"},
    "/api/leagues/t/trade-assets?roster_id=2": {
        "gsis_id", "full_name", "position", "ros_points", "label",
    },
    "/api/leagues/t/player-weeks?gsis_id=G_QB&n=2": {"week", "projection"},
    "/api/leagues/t/outlook?scope=mine": {
        "gsis_id", "full_name", "position", "owner", "recent_ppg", "expected_ppg", "next_ppg",
        "change", "chance_to_play", "label", "why",
    },
    "/api/leagues/t/outlook?scope=free": {
        "gsis_id", "full_name", "position", "owner", "recent_ppg", "expected_ppg", "next_ppg",
        "change", "chance_to_play", "label", "why",
    },
}  # fmt: skip


@pytest.mark.parametrize("path", ROWS)
def test_row_routes_return_an_ok_envelope_with_the_expected_columns(
    path: str, client: TestClient
) -> None:
    out = body(client.get(f"{path}"))
    assert out["status"] == "ok", out
    if path.endswith("live-score"):  # the fixture has no matchup in play: only the envelope
        assert out["data"] == []
        return
    assert columns(out["data"]) == ROWS[path]


def test_free_scope_and_empty_results_are_ok_with_no_rows(client: TestClient) -> None:
    out = body(client.get("/api/leagues/t/player-weeks?gsis_id=nobody"))
    assert out == {"status": "ok", "data": [], "error": None, "started_at": None}


def test_unmatched_lists_names(client: TestClient) -> None:
    data = body(client.get("/api/unmatched"))["data"]
    assert data["count"] == len(data["names"]) and "nogsis (WR, KC)" in data["names"]


def test_bad_query_values_are_rejected(client: TestClient) -> None:
    assert client.get("/api/leagues/t/streamers?kind=QB").status_code == 422
    assert client.get("/api/leagues/t/outlook?scope=x").status_code == 422
    assert client.get("/api/leagues/t/player-weeks").status_code == 422


def wait_ok(client: TestClient, send: Callable[[], Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def done() -> bool:
        r = send()
        if r.status_code == 200:
            result.update(r.json())
            return True
        assert r.status_code == 202, r.text
        return False

    wait_until(done)
    return result


def test_win_probability_job_returns_options_swap_and_every_objective(client: TestClient) -> None:
    out = wait_ok(client, lambda: client.get("/api/leagues/t/win-probability?week=3"))
    assert out["status"] == "ok"
    data = out["data"]
    assert set(data) == {"script", "swap", "comparison", "options", "lineups", "summaries"}
    assert [r["option"] for r in data["comparison"]][0] == "Expected points"
    assert set(data["lineups"]) == set(data["summaries"]) == {
        "expected_points", "win_probability", "max_ceiling", "max_floor",
    }  # fmt: skip
    assert columns(data["lineups"]["max_floor"]) == LINEUP
    assert data["swap"]["differs"] is False


def test_actions_and_waivers_jobs_return_rows(client: TestClient, store_dir: Path) -> None:
    write_rows(store_dir, "trending")
    actions = wait_ok(client, lambda: client.get("/api/leagues/t/actions"))
    assert actions["status"] == "ok" and isinstance(actions["data"], list)
    assert all({"delta_points", "share_better"} <= r.keys() for r in actions["data"])
    waivers = wait_ok(client, lambda: client.get("/api/leagues/t/waivers"))
    assert waivers["status"] == "ok"
    assert isinstance(waivers["data"], list)  # the fixture's free agent adds nothing


def test_trade_evaluate_returns_odds_and_roster_changes_in_one_response(
    client: TestClient,
) -> None:
    payload = {"partner_roster_id": 2, "give_ids": ["G_QB", "G_WR"], "get_ids": ["G_OPP"]}
    out = body(client.post("/api/leagues/t/trades/evaluate", json=payload))
    assert out["status"] == "ok"
    data = out["data"]
    assert {r["side"] for r in data["odds"]} == {"me", "them"}
    assert data["roster_changes"][0]["action"] == "picked up"
    assert data["warning"] == "Automatic roster moves to keep sizes equal:"
    assert data["trade_deadline"] is None


def test_trade_evaluate_validates_the_body(client: TestClient) -> None:
    assert client.post("/api/leagues/t/trades/evaluate", json={}).status_code == 422


def test_trade_find_is_a_job(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # the tiny store is too small for the finder's screen (it needs six players a side)
    found = {
        "partner": ["Theirs"],
        "give": ["a (WR)"],
        "get": ["b (RB)"],
        "give_ids": [["a"]],
        "get_ids": [["b"]],
        "kind": ["need swap"],
        "my_fills": ["RB"],
        "their_fills": ["WR"],
        "my_fit": [9.0],
        "their_fit": [4.0],
    }
    found |= {k: [0.01] for k in ("my_playoff", "my_title", "their_playoff", "their_title")}
    found["se_title"] = [0.01]
    monkeypatch.setattr(data_api, "find_trades", lambda league: pl.DataFrame(found))
    out = wait_ok(client, lambda: client.post("/api/leagues/t/trades/find"))
    assert out["status"] == "ok" and out["data"][0]["partner"] == "Theirs"


# --- OpenAPI snapshot -----------------------------------------------------------------


def test_openapi_snapshot_matches_the_app() -> None:
    committed = json.loads((ROOT / "web" / "openapi.json").read_text())
    assert committed == json.loads(json.dumps(api.create_app().openapi()))
    assert all(p.startswith("/api/") or p == "/api" for p in committed["paths"])


# --- hardening ------------------------------------------------------------------------


def test_post_without_the_csrf_header_is_a_403_error_envelope(store_dir: Path) -> None:
    with TestClient(api.create_app(), base_url="http://localhost") as bare:
        r = bare.post("/api/live/refresh")
        assert r.status_code == 403 and r.json()["status"] == "error"
        assert r.json()["error"]["code"] == "invalid"
        assert bare.get("/api/status").status_code == 200  # reads need no header


def test_origin_must_be_an_allowed_host(client: TestClient) -> None:
    assert client.get("/api/status", headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"Origin": "null"}).status_code == 403
    assert client.get("/api/status", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_trade_request_is_bounded(client: TestClient) -> None:
    url = "/api/leagues/t/trades/evaluate"
    ok_ids = {"partner_roster_id": 2, "give_ids": ["a"], "get_ids": ["b"]}
    for patch in (
        {"give_ids": []},
        {"get_ids": ["x"] * 11},
        {"give_ids": ["x" * 65]},
    ):
        assert client.post(url, json=ok_ids | patch).status_code == 422


def test_trade_evaluate_says_busy_when_all_slots_are_taken(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(api_routes, "TRADE_SLOTS", full)
    payload = {"partner_roster_id": 2, "give_ids": ["G_QB"], "get_ids": ["G_OPP"]}
    out = body(client.post("/api/leagues/t/trades/evaluate", json=payload))
    assert out["error"]["code"] == "busy"


def test_job_for_an_unknown_league_is_invalid_and_starts_no_job(client: TestClient) -> None:
    out = body(client.get("/api/leagues/zzz/actions"))
    assert out["error"]["code"] == "invalid"
    assert client.app.state.runner._jobs == {}  # type: ignore[attr-defined]


def test_job_runner_caps_running_jobs_and_remembers_few_finished_ones() -> None:
    runner = JobRunner(max_workers=2)
    gate = threading.Event()
    for i in range(8):
        runner.submit(("e", (i,), "v"), lambda: gate.wait(5))
    with pytest.raises(Busy):
        runner.submit(("e", (99,), "v"), lambda: 1)
    gate.set()
    wait_until(lambda: all(j.future.done() for j in runner._jobs.values()))
    for i in range(100, 180):
        runner.submit(("e", (i,), "v"), lambda: 1).future.result(5)
    assert len(runner._jobs) <= 64
    runner.shutdown()


def test_concurrent_cache_misses_build_the_league_once(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fantasy.stages import simulate

    calls: list[int] = []
    real = simulate.load_league_data

    def slow(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(simulate, "load_league_data", slow)
    threads = [threading.Thread(target=_engine._league, args=("t",)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_a_job_builds_its_league_under_the_version_in_its_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    versions = iter(["v1", "v2"])
    monkeypatch.setattr(api_routes, "data_version", lambda: next(versions))
    monkeypatch.setattr(
        _engine, "_league_cached", lambda key, version, d: seen.append(version) or (None, 1)
    )
    monkeypatch.setattr(
        data_api, "actions", lambda league: _engine._league(league) and pl.DataFrame()
    )
    client.get("/api/leagues/t/actions")
    wait_until(lambda: all(j.future.done() for j in client.app.state.runner._jobs.values()))  # type: ignore[attr-defined]
    assert seen == ["v1"]


def test_refresh_second_caller_gets_busy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(data_api, "refresh_live", lambda: 1)
    assert api_routes.REFRESH_LOCK.acquire(blocking=False)
    try:
        assert body(client.post("/api/live/refresh"))["error"]["code"] == "busy"
    finally:
        api_routes.REFRESH_LOCK.release()
    assert body(client.post("/api/live/refresh"))["status"] == "ok"


def test_refresh_failure_message_is_fixed_and_hides_the_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> int:
        raise httpx.ConnectError("secret-host.internal refused")

    monkeypatch.setattr(data_api, "refresh_live", broken)
    out = body(client.post("/api/live/refresh"))
    assert out["status"] == "error" and "secret" not in out["error"]["message"]


def test_unexpected_exceptions_become_a_server_error_without_the_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> pl.DataFrame:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(data_api, "lineup", boom)
    out = body(client.get("/api/leagues/t/lineup"))
    assert out["error"]["code"] == "server" and "secret" not in out["error"]["message"]
