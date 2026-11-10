import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows

from fantasy import _engine, _live, api, api_envelope, api_routes, data_api
from fantasy._lock import pipeline_lock
from fantasy.api_jobs import Busy, JobRunner
from fantasy.sim.availability import kickoffs
from fantasy.sources import sleeper

ROOT = Path(__file__).resolve().parents[3]
CSRF_HEADER = {"X-Requested-With": "fantasy-app"}
LEAGUE_ROWS = [
    {"league_key": "t", "league_id": "L1", "name": "Test", "roster_id": 1},
]


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
    assert set(data) == {
        "freshness",
        "missing_layers",
        "simulation_behind_inputs",
        "refresh_runs",
        "data_version",
        "live_refresh",
    }
    assert "injury model" in data["missing_layers"]
    assert {r["source"] for r in data["freshness"]} >= {"Sleeper"}


def test_leagues_has_record_fallback_and_trade_deadline(client: TestClient) -> None:
    rows = body(client.get("/api/leagues"))["data"]
    assert [r["league_key"] for r in rows] == ["t"]
    assert rows[0]["record"] == "no record yet" and rows[0]["trade_deadline"] is None
    assert rows[0]["team_name"] == "Mine"


def test_data_version_follows_the_files_of_the_given_data_dir(tmp_path: Path) -> None:
    assert _engine.data_version(tmp_path) == "0-0"
    (tmp_path / "raw").mkdir(parents=True)
    (tmp_path / "raw" / "a.parquet").write_bytes(b"12345")
    first = _engine.data_version(tmp_path)
    assert first.endswith("-5")
    (tmp_path / "raw" / "a.parquet").write_bytes(b"123456")
    assert _engine.data_version(tmp_path) != first


def count_builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from fantasy.sim import league_data as simulate

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
    monkeypatch.setattr(_live, "refresh_live", lambda data_dir: 7)
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


def test_a_row_that_drifts_from_its_model_is_a_500_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = data_api.leagues
    monkeypatch.setattr(
        data_api,
        "leagues",
        lambda *a, **k: original(*a, **k).with_columns(surprise=pl.lit(1)),
    )

    r = client.get("/api/leagues")

    assert r.status_code == 500
    out = r.json()
    assert out["status"] == "error" and out["error"]["code"] == "server"
    assert out["error"]["message"] == api_envelope.SERVER_MESSAGE


def test_a_validation_error_is_an_envelope_with_the_field(client: TestClient) -> None:
    r = client.get("/api/leagues/t/scoreboard?week=99")

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid"
    assert r.json()["error"]["message"].startswith("week: ")


def test_an_unknown_api_path_is_a_404_envelope(client: TestClient) -> None:
    r = client.get("/api/nope")

    assert r.status_code == 404
    assert r.json()["status"] == "error"


# --- hosts and static files -----------------------------------------------------------


def test_unknown_host_header_is_rejected(store_dir: Path) -> None:
    with TestClient(api.create_app(data_dir=store_dir), base_url="http://evil.example") as c:
        assert c.get("/api/status").status_code == 400


def test_hosts_from_the_environment_are_allowed(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_ALLOWED_HOSTS", "box.tail1234.ts.net, other.local")
    with TestClient(api.create_app(data_dir=store_dir), base_url="http://box.tail1234.ts.net") as c:
        assert c.get("/api/status").status_code == 200
    with TestClient(api.create_app(data_dir=store_dir), base_url="http://127.0.0.1") as c:
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


def test_deep_links_serve_the_app_but_unknown_api_paths_stay_404(
    store_dir: Path, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>hi</html>")
    with TestClient(api.create_app(web_dist=dist), base_url="http://localhost") as c:
        assert "hi" in c.get("/lineup").text
        assert c.get("/api/nope").status_code == 404
        assert "hi" not in c.get("/api/nope").text
        assert c.get("/assets/missing.js").status_code == 404


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
    "recommended", "injury", "injury_note", "locked", "actual", "game", "change", "swap_in",
}  # fmt: skip
ROWS = {
    "/api/leagues/t/roster": {
        "sleeper_id", "full_name", "position", "team", "injury_status", "is_starter", "is_ir",
    },
    "/api/leagues/t/season-odds": {
        "roster_id", "team_name", "p_playoffs", "p_bye", "p_title", "exp_wins", "is_me",
    },
    "/api/leagues/t/seeds": {"seed", "p"},
    "/api/leagues/t/odds-history": {
        "run_at", "as_of_week", "team_name", "roster_id", "p_playoffs", "p_title",
    },
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
        "change", "chance_to_play", "next_game", "label", "why",
    },
    "/api/leagues/t/outlook?scope=free": {
        "gsis_id", "full_name", "position", "owner", "recent_ppg", "expected_ppg", "next_ppg",
        "change", "chance_to_play", "next_game", "label", "why",
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


def test_owners_lists_every_rostered_player_and_follows_the_viewed_team(
    client: TestClient,
) -> None:
    def owners(path: str) -> dict[str, tuple[str, bool]]:
        data = body(client.get(path))["data"]["rows"]
        return {r["gsis_id"]: (r["owner"], r["is_mine"]) for r in data}

    first = body(client.get("/api/leagues/t/owners"))["data"]["rows"]
    assert set(first[0]) == {"gsis_id", "owner", "roster_id", "is_mine"}
    assert all(r["gsis_id"] for r in first)  # no null ids
    mine = owners("/api/leagues/t/owners")
    assert mine["G_QB"] == ("Mine", True)  # the real team name, not "You"
    assert mine["G_OPP"] == ("Theirs", False)
    by_id = {r["gsis_id"]: r["roster_id"] for r in first}
    assert (by_id["G_QB"], by_id["G_OPP"]) == (1, 2)  # the id tells apart teams that share a name
    assert "G_FA" not in mine  # a free agent has no owner, so no row
    viewed = owners("/api/leagues/t/owners?team=2")
    assert viewed["G_OPP"] == ("Theirs", True) and viewed["G_QB"] == ("Mine", False)


def test_owners_counts_rostered_skill_players_without_an_nflverse_id(
    client: TestClient,
) -> None:
    # the fixture's "nogsis" WR is rostered but has no crosswalk id; K and DEF are not counted
    assert body(client.get("/api/leagues/t/owners"))["data"]["unmatched"] == 1


def test_owners_errors_follow_the_sibling_routes(client: TestClient) -> None:
    for path in ("/api/leagues/zzz/owners", "/api/leagues/t/owners?team=99"):
        out = body(client.get(path))
        assert out["status"] == "error" and out["data"] is None
        assert out["error"]["code"] == "invalid"


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
    assert data["comparison"][0]["option"] == "Expected points"
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
    monkeypatch.setattr(data_api, "find_trades", lambda league, data_dir, team: pl.DataFrame(found))
    out = wait_ok(client, lambda: client.post("/api/leagues/t/trades/find"))
    assert out["status"] == "ok" and out["data"][0]["partner"] == "Theirs"


# --- OpenAPI snapshot -----------------------------------------------------------------


def test_openapi_snapshot_matches_the_app(tmp_path: Path) -> None:
    committed = json.loads((ROOT / "web" / "openapi.json").read_text())
    live = json.loads(json.dumps(api.create_app(data_dir=tmp_path).openapi()))
    assert committed == live, (
        "web/openapi.json is stale: regenerate with "
        "`uv run python -m fantasy.api --openapi > web/openapi.json`, "
        "then `cd web && npm run types`"
    )
    assert all(p.startswith("/api/") or p == "/api" for p in committed["paths"])


# --- hardening ------------------------------------------------------------------------


def test_post_without_the_csrf_header_is_a_403_error_envelope(store_dir: Path) -> None:
    with TestClient(api.create_app(data_dir=store_dir), base_url="http://localhost") as bare:
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
    patches: tuple[dict[str, list[str]], ...] = (
        {"give_ids": []},
        {"get_ids": ["x"] * 11},
        {"give_ids": ["x" * 65]},
    )
    for patch in patches:
        assert client.post(url, json=ok_ids | patch).status_code == 422


def test_trade_evaluate_says_busy_when_all_slots_are_taken(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(api_routes.jobs, "TRADE_SLOTS", full)
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
    from fantasy.sim import league_data as simulate

    calls: list[int] = []
    real = simulate.load_league_data

    def slow(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(simulate, "load_league_data", slow)
    threads = [threading.Thread(target=_engine._league, args=("t", store_dir)) for _ in range(4)]
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
    monkeypatch.setattr(api_routes.common, "data_version", lambda data_dir: next(versions))

    def cached(key: str, version: str, d: str) -> tuple[None, int]:
        seen.append(version)
        return None, 1

    monkeypatch.setattr(_engine, "_league_cached", cached)
    monkeypatch.setattr(
        data_api,
        "actions",
        lambda league, **kw: _engine._league(league, kw["data_dir"]) and pl.DataFrame(),
    )
    client.get("/api/leagues/t/actions")
    wait_until(lambda: all(j.future.done() for j in client.app.state.runner._jobs.values()))  # type: ignore[attr-defined]
    assert seen == ["v1"]


def test_refresh_second_caller_gets_busy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_live, "refresh_live", lambda data_dir: 1)
    with pipeline_lock(client.app.state.data_dir):  # type: ignore[attr-defined]
        assert body(client.post("/api/live/refresh"))["error"]["code"] == "busy"
    assert body(client.post("/api/live/refresh"))["status"] == "ok"


def test_refresh_failure_message_is_fixed_and_hides_the_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(*args: Any, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("secret-host.internal refused")

    # fail inside the real Sleeper client so the route sees the exception it really raises
    monkeypatch.setattr(httpx, "get", refused)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(_live, "refresh_live", lambda data_dir: sleeper.fetch("/state/nfl"))
    out = body(client.post("/api/live/refresh"))
    assert out["status"] == "error" and out["error"]["message"].startswith("Sleeper refresh failed")
    assert "secret" not in out["error"]["message"]


def test_unexpected_exceptions_become_a_server_error_without_the_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> pl.DataFrame:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(data_api, "lineup", boom)
    response = client.get("/api/leagues/t/lineup")
    out = response.json()
    assert response.status_code == 500
    assert out["error"]["code"] == "server" and "secret" not in out["error"]["message"]


def test_scoreboard_returns_one_nested_row_per_matchup_and_follows_the_team(
    client: TestClient,
) -> None:
    out = body(client.get("/api/leagues/t/scoreboard"))
    assert out["status"] == "ok", out
    first = out["data"][0]
    assert set(first) == {"week", "matchup_id", "status", "a", "b"}
    assert first["a"]["is_me"] and first["a"]["team_name"] == "Mine"
    assert first["a"]["win_prob"] + first["b"]["win_prob"] == pytest.approx(1.0)
    other = body(client.get("/api/leagues/t/scoreboard?team=5"))["data"][0]
    assert other["matchup_id"] == 3 and other["a"]["is_me"]
    assert client.get("/api/leagues/t/scoreboard?week=99").status_code == 422


def test_scorecard_is_an_empty_ok_envelope_before_anything_is_archived(
    client: TestClient,
) -> None:
    out = body(client.get("/api/leagues/t/scorecard"))
    assert out["status"] == "ok", out
    assert out["data"]["rows"] == [] and out["data"]["weeks_archived"] == []
    assert out["data"]["has_quantiles"] is False
    assert body(client.get("/api/leagues/nope/scorecard"))["error"]["code"] == "invalid"


def test_player_points_serves_one_players_weekly_points_for_the_league(
    client: TestClient, store_dir: Path
) -> None:
    rows = [
        {"league_id": lid, "gsis_id": g, "season": s, "week": w, "points": p}
        | {"season_type": "REG", "position": "WR"}
        for lid, g, s, w, p in (
            ("L1", "G_WR", 2026, 2, 11.5),
            ("L1", "G_WR", 2026, 1, 7.0),
            ("L1", "G_WR", 2025, 1, 99.0),
            ("L1", "G_OTHER", 2026, 1, 50.0),
            ("L2", "G_WR", 2026, 1, 60.0),
        )
    ]
    write_rows(store_dir, "player_points", rows)
    out = body(client.get("/api/leagues/t/player-points?gsis_id=G_WR&season=2026"))
    assert out["data"] == [
        {"gsis_id": "G_WR", "week": 1, "points": 7.0},
        {"gsis_id": "G_WR", "week": 2, "points": 11.5},
    ]
    empty = body(client.get("/api/leagues/t/player-points?gsis_id=NOBODY&season=2026"))
    assert empty["data"] == []


def test_player_points_without_a_player_serves_everyone_for_that_league_and_season(
    client: TestClient, store_dir: Path
) -> None:
    rows = [
        {"league_id": lid, "gsis_id": g, "season": s, "week": w, "points": p, "season_type": t}
        | {"position": "WR"}
        for lid, g, s, w, p, t in (
            ("L1", "G_WR", 2026, 2, 11.5, "REG"),
            ("L1", "G_WR", 2026, 1, 7.0, "REG"),
            ("L1", "G_OTHER", 2026, 1, 50.0, "REG"),
            ("L1", "G_OTHER", 2026, 19, 5.0, "POST"),
            ("L1", "G_WR", 2025, 1, 99.0, "REG"),
            ("L2", "G_WR", 2026, 1, 60.0, "REG"),
        )
    ]
    write_rows(store_dir, "player_points", rows)
    out = body(client.get("/api/leagues/t/player-points?season=2026"))
    assert out["status"] == "ok", out
    assert out["data"] == [
        {"gsis_id": "G_OTHER", "week": 1, "points": 50.0},
        {"gsis_id": "G_WR", "week": 1, "points": 7.0},
        {"gsis_id": "G_WR", "week": 2, "points": 11.5},
    ]
    assert body(client.get("/api/leagues/t/player-points?season=2031"))["data"] == []


def test_player_points_reads_the_league_id_without_building_the_simulation(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fantasy import _market

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("player_points must not build LeagueData")

    monkeypatch.setattr(_market, "_league", forbidden)
    row = {"league_id": "L1", "gsis_id": "G_WR", "season": 2026, "week": 1, "points": 7.0}
    write_rows(store_dir, "player_points", [row | {"season_type": "REG", "position": "WR"}])
    out = data_api.player_points("t", "G_WR", 2026, store_dir)
    assert out.rows() == [("G_WR", 1, 7.0)]
    with pytest.raises(ValueError, match="unknown league 'zzz'"):
        data_api.player_points("zzz", None, 2026, store_dir)


def test_data_version_parses_the_schedule_once_per_file_state(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = kickoffs

    def counted(*a: Any) -> Any:
        calls.append(1)
        return real(*a)

    monkeypatch.setattr(_engine, "kickoffs", counted)
    first = _engine.data_version(store_dir)
    assert _engine.data_version(store_dir) == first
    assert len(calls) == 1
    path = store_dir / "raw" / "nfl_schedules.parquet"
    stamp = path.stat().st_mtime + 5
    os.utime(path, (stamp, stamp))  # any change to the file is seen on the next call
    assert _engine.data_version(store_dir) != first
    assert len(calls) == 2


def test_known_league_treats_missing_tables_as_before(store_dir: Path, tmp_path: Path) -> None:
    assert api_routes.common.known_league("t", store_dir)
    assert not api_routes.common.known_league("zzz", store_dir)
    assert not api_routes.common.known_league(
        "t", tmp_path / "empty"
    )  # old read gave an empty frame
    (store_dir / "raw" / "league_teams.parquet").unlink()
    assert api_routes.common.known_league(
        "t", store_dir
    )  # old join read the missing table as empty


def test_data_version_without_a_schedule_has_no_clock_bucket_until_it_appears(
    store_dir: Path,
) -> None:
    path = store_dir / "raw" / "nfl_schedules.parquet"
    saved = path.read_bytes()
    path.unlink()
    assert _engine.data_version(store_dir).isdigit() is False  # "<mtime>-<size>", no bucket
    assert "@" not in _engine.data_version(store_dir)
    path.write_bytes(saved)
    assert _engine.data_version(store_dir) != ""


def test_player_points_errors_follow_the_sibling_routes(client: TestClient) -> None:
    out = body(client.get("/api/leagues/zzz/player-points?gsis_id=G_WR&season=2026"))
    assert out["status"] == "error" and out["data"] is None
    assert out["error"]["code"] == "invalid"
    assert client.get("/api/leagues/t/player-points?gsis_id=G_WR&season=1900").status_code == 422
    assert client.get("/api/leagues/t/player-points").status_code == 422
    all_players = body(client.get("/api/leagues/zzz/player-points?season=2026"))
    assert all_players["error"]["code"] == "invalid"


def test_player_profile_serves_range_and_ros_over_replacement(client: TestClient) -> None:
    out = body(client.get("/api/leagues/t/players/G_QB/profile"))
    assert out["status"] == "ok"
    assert out["data"]["gsis_id"] == "G_QB"
    assert out["data"]["p10"] < out["data"]["median"] < out["data"]["p90"]
    assert "ros_over_replacement" in out["data"]
    assert body(client.get("/api/leagues/zzz/players/G_QB/profile"))["status"] == "error"


def test_player_profile_rejects_a_malformed_id(client: TestClient) -> None:
    assert client.get("/api/leagues/t/players/bad%20id/profile").status_code == 422
    assert client.get(f"/api/leagues/t/players/{'x' * 21}/profile").status_code == 422


def test_status_returns_the_latest_run_per_stage(client: TestClient, store_dir: Path) -> None:
    from datetime import UTC, datetime

    from fantasy import _runs

    _runs.record_run("digest", "failed", "boom", store_dir, now=datetime(2026, 11, 1, tzinfo=UTC))
    _runs.record_run("digest", "failed", "down", store_dir, now=datetime(2026, 11, 2, tzinfo=UTC))
    _runs.record_run("score", "ok", None, store_dir, now=datetime(2026, 11, 2, tzinfo=UTC))
    runs = body(client.get("/api/status"))["data"]["refresh_runs"]
    assert {(r["stage"], r["status"], r["error"]) for r in runs} == {
        ("digest", "failed", "down"),
        ("score", "ok", None),
    }
    assert set(runs[0]) == {"stage", "finished_at", "status", "error"}


def test_serving_keeps_the_access_log_off_so_invite_tokens_stay_out_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    from fantasy import api

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(kwargs))
    api.main([])
    assert seen["access_log"] is False
