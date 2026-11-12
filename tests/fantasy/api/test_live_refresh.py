from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows

from fantasy import api, data_api, live_refresh, store
from fantasy._engine import current_week
from fantasy._lock import pipeline_lock
from fantasy.api_jobs import JobRunner
from fantasy.live_refresh import LIVE_REFRESH_MINUTES, LiveRefresher
from fantasy.sim.availability import GAME_MINUTES, LIVE_WINDOW_PAD_MINUTES, games_on
from fantasy.stages import simulate, sync_sleeper

KICK = datetime(2026, 10, 25, 17, 0, tzinfo=UTC)
END = KICK + timedelta(minutes=GAME_MINUTES + LIVE_WINDOW_PAD_MINUTES)
CSRF = {"X-Requested-With": "fantasy-app"}


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The pipeline lock lives in the data folder; keep these tests off the real one."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    return tmp_path


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
    monkeypatch.setattr(live_refresh, "current_week_kickoffs", lambda data_dir: (8, {"A": KICK}))

    def sync(week: int, data_dir: Path | None) -> int:
        log.append(f"sync{week}")
        return 1

    monkeypatch.setattr(sync_sleeper, "sync_week", sync)
    monkeypatch.setattr(
        simulate, "run", lambda *a, **k: log.append(f"sim archive={k.get('archive')}")
    )
    monkeypatch.setattr(live_refresh, "_clear_league_cache", lambda: log.append("clear"))
    monkeypatch.setattr(data_api, "record_live_tick", lambda now, data_dir: log.append("record"))
    return log


def refresher() -> LiveRefresher:
    return LiveRefresher(JobRunner(), enabled=True)


def test_tick_syncs_then_simulates_without_archive_then_clears(calls: list[str]) -> None:
    live = refresher()
    assert live.step(KICK)
    assert calls == ["sync8", "sim archive=False", "record", "clear"]
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
    assert len(calls) == n + 4
    assert not live.step(END + timedelta(minutes=2))
    assert not live.status()["active"]


def test_skips_when_manual_refresh_holds_the_lock(calls: list[str]) -> None:
    live = refresher()
    with pipeline_lock():
        assert not live.step(KICK)
    assert calls == []
    assert live.step(KICK + timedelta(seconds=30))  # a skip is not an attempt: retried at once


def test_error_is_recorded_lock_released_and_next_tick_runs(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    live = refresher()

    def boom(week: int, data_dir: object) -> int:
        raise OSError("sleeper down")

    monkeypatch.setattr(sync_sleeper, "sync_week", boom)
    assert not live.step(KICK)
    assert "OSError: sleeper down" in (live.status()["last_error"] or "")
    assert not live.step(KICK + timedelta(minutes=1))  # no tight retry
    with pipeline_lock(blocking=False):  # the failed tick released the lock
        pass

    def sync(week: int, data_dir: Path | None) -> int:
        calls.append("sync")
        return 1

    monkeypatch.setattr(sync_sleeper, "sync_week", sync)
    assert live.step(KICK + timedelta(minutes=LIVE_REFRESH_MINUTES))
    assert live.status()["last_error"] is None


def test_current_week_is_the_highest_and_none_without_one() -> None:
    assert current_week(pl.DataFrame({"current_week": [8, None, 9]})) == 9
    assert current_week(pl.DataFrame(schema={"current_week": pl.Int64})) is None


def test_schedule_read_failure_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(data_dir: object) -> Any:
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
    store_dir: Path,
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


def test_simulate_run_archives_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appended: list[int] = []
    monkeypatch.setattr(simulate, "append_history", lambda latest, data_dir: appended.append(1))
    write_rows(tmp_path, "leagues")  # no leagues: nothing to simulate, the tables are still written
    simulate.run(n_sims=1, archive=False, data_dir=tmp_path)
    assert appended == []
    simulate.run(n_sims=1, data_dir=tmp_path)
    assert appended == [1]


def test_a_failing_history_write_does_not_stop_the_tick_clearing_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log: list[str] = []
    monkeypatch.setattr(live_refresh, "current_week_kickoffs", lambda data_dir: (8, {"A": KICK}))
    monkeypatch.setattr(sync_sleeper, "sync_week", lambda week, data_dir: 1)
    monkeypatch.setattr(simulate, "run", lambda *a, **k: None)
    monkeypatch.setattr(live_refresh, "_clear_league_cache", lambda: log.append("clear"))
    # no tables in tmp_path: recording the day history fails, and must not fail the tick
    assert LiveRefresher(JobRunner(), enabled=True, data_dir=tmp_path).step(KICK)
    assert log == ["clear"]
