from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient
from test_api import store_dir as store_dir  # noqa: F401 - fixture

from fantasy import api, api_routes, live_refresh, store
from fantasy.api_jobs import JobRunner
from fantasy.live_refresh import LIVE_REFRESH_MINUTES, LiveRefresher
from fantasy.sim.availability import GAME_MINUTES, LIVE_WINDOW_PAD_MINUTES, games_on
from fantasy.stages import simulate, sync_sleeper

KICK = datetime(2026, 10, 25, 17, 0, tzinfo=UTC)
END = KICK + timedelta(minutes=GAME_MINUTES + LIVE_WINDOW_PAD_MINUTES)
CSRF = {"X-Requested-With": "fantasy-app"}


def test_games_on_boundaries() -> None:
    kicks = {"A": KICK, "B": KICK}
    assert not games_on(kicks, KICK - timedelta(seconds=1))
    assert games_on(kicks, KICK)
    assert games_on(kicks, END - timedelta(seconds=1))
    assert not games_on(kicks, END)
    assert not games_on({}, KICK)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    log: list[str] = []
    monkeypatch.setattr(live_refresh, "current_week_kickoffs", lambda: (8, {"A": KICK}))
    monkeypatch.setattr(sync_sleeper, "sync_week", lambda week: log.append(f"sync{week}") or 1)
    monkeypatch.setattr(
        simulate, "run", lambda *a, **k: log.append(f"sim archive={k.get('archive')}")
    )
    monkeypatch.setattr(live_refresh, "_clear_league_cache", lambda: log.append("clear"))
    return log


def refresher() -> LiveRefresher:
    return LiveRefresher(JobRunner(), enabled=True)


def test_tick_syncs_then_simulates_without_archive_then_clears(calls: list[str]) -> None:
    live = refresher()
    assert live.step(KICK)
    assert calls == ["sync8", "sim archive=False", "clear"]
    assert live.status()["last_ok_at"] == KICK.isoformat(timespec="seconds")
    assert live.status()["active"]


def test_no_tick_when_no_game_is_on(calls: list[str]) -> None:
    assert not refresher().step(KICK - timedelta(hours=1))
    assert calls == []


def test_ticks_every_interval_and_once_more_after_close(calls: list[str]) -> None:
    live = refresher()
    live.step(KICK)
    assert not live.step(KICK + timedelta(minutes=LIVE_REFRESH_MINUTES - 1))
    assert live.step(KICK + timedelta(minutes=LIVE_REFRESH_MINUTES))
    live.step(END - timedelta(minutes=1))
    n = len(calls)
    assert live.step(END + timedelta(minutes=1))  # final tick, before the next interval is due
    assert len(calls) == n + 3
    assert not live.step(END + timedelta(minutes=2))
    assert not live.status()["active"]


def test_skips_when_manual_refresh_holds_the_lock(calls: list[str]) -> None:
    live = refresher()
    assert api_routes.REFRESH_LOCK.acquire(blocking=False)
    try:
        assert not live.step(KICK)
    finally:
        api_routes.REFRESH_LOCK.release()
    assert calls == []
    assert live.step(KICK + timedelta(seconds=30))  # a skip is not an attempt: retried at once


def test_error_is_recorded_lock_released_and_next_tick_runs(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live = refresher()

    def boom(week: int) -> int:
        raise OSError("sleeper down")

    monkeypatch.setattr(sync_sleeper, "sync_week", boom)
    assert not live.step(KICK)
    assert "OSError: sleeper down" in (live.status()["last_error"] or "")
    assert not live.step(KICK + timedelta(minutes=1))  # no tight retry
    assert not api_routes.REFRESH_LOCK.locked()
    monkeypatch.setattr(sync_sleeper, "sync_week", lambda week: calls.append("sync") or 1)
    assert live.step(KICK + timedelta(minutes=LIVE_REFRESH_MINUTES))
    assert live.status()["last_error"] is None


def test_schedule_read_failure_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> Any:
        raise FileNotFoundError("nfl_schedules")

    monkeypatch.setattr(live_refresh, "current_week_kickoffs", missing)
    live = refresher()
    assert not live.step(KICK)
    assert "FileNotFoundError" in (live.status()["last_error"] or "")


def test_env_off_disables_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_REFRESH", "off")
    live = LiveRefresher(JobRunner())
    live.start()
    assert not live.enabled and live._thread is None
    assert live.status()["enabled"] is False and live.status()["active"] is False


def test_lifespan_starts_and_stops_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE_REFRESH", raising=False)
    monkeypatch.setattr(live_refresh, "POLL_SECONDS", 3600)
    app = api.create_app()
    live: LiveRefresher = app.state.live
    with TestClient(app, base_url="http://localhost", headers=CSRF):
        thread = live._thread
        assert thread is not None and thread.is_alive()
    assert not thread.is_alive() and live._thread is None


def test_status_route_reports_live_refresh(
    store_dir: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVE_REFRESH", "off")
    with TestClient(api.create_app(), base_url="http://localhost", headers=CSRF) as client:
        out = client.get("/api/status").json()
    assert out["status"] == "ok"
    assert out["data"]["live_refresh"] == {
        "enabled": False,
        "active": False,
        "last_ok_at": None,
        "last_error": None,
        "interval_minutes": LIVE_REFRESH_MINUTES,
    }


def test_simulate_run_archives_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    appended: list[int] = []
    monkeypatch.setattr(simulate, "append_history", lambda latest: appended.append(1))
    monkeypatch.setattr(store, "read_table", lambda *a, **k: pl.DataFrame({"league_id": []}))
    monkeypatch.setattr(store, "write_table", lambda *a, **k: None)
    simulate.run(n_sims=1, archive=False)
    assert appended == []
    simulate.run(n_sims=1)
    assert appended == [1]
