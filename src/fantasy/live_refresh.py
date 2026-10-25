"""Light live refresh inside `make serve`: every LIVE_REFRESH_MINUTES while a game of the
league's current week is on, pull Sleeper scores and re-run the simulation (no archive append).
`LIVE_REFRESH=off` disables it."""

import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fantasy import api_routes, data_api, store
from fantasy._engine import _clear_league_cache
from fantasy.api_jobs import JobRunner
from fantasy.config import load_config
from fantasy.sim.availability import games_on, kickoffs
from fantasy.stages import simulate, sync_sleeper

log = logging.getLogger(__name__)
LIVE_REFRESH_MINUTES = 10
POLL_SECONDS = 30
ENV_VAR = "LIVE_REFRESH"


def enabled_by_env() -> bool:
    return os.environ.get(ENV_VAR, "on").strip().lower() != "off"


def current_week_kickoffs() -> tuple[int, dict[str, datetime]]:
    week = int(data_api.leagues()["current_week"].to_numpy().max())
    schedules = store.read_table("nfl_schedules", "raw")
    return week, kickoffs(schedules, load_config().season, week)


@dataclass
class LiveState:
    active: bool = False
    last_ok_at: str | None = None
    last_error: str | None = None


class LiveRefresher:
    def __init__(self, runner: JobRunner, enabled: bool | None = None) -> None:
        self.runner = runner
        self.enabled = enabled_by_env() if enabled is None else enabled
        self.state = LiveState()
        self._last_attempt: datetime | None = None
        self._was_active = False
        self._last_error_text: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def status(self) -> dict[str, Any]:
        s = self.state
        return {
            "enabled": self.enabled,
            "active": self.enabled and s.active,
            "last_ok_at": s.last_ok_at,
            "last_error": s.last_error,
            "interval_minutes": LIVE_REFRESH_MINUTES,
        }

    def step(self, now: datetime) -> bool:
        """One wake: run a tick if due. Returns whether a tick ran. Never raises."""
        try:
            week, kicks = current_week_kickoffs()
            active = games_on(kicks, now)
            closing = self._was_active and not active  # one last tick once the window closes
            self._was_active = self.state.active = active
            if not (active or closing):
                return False
            interval = timedelta(minutes=LIVE_REFRESH_MINUTES)
            due = closing or self._last_attempt is None or now - self._last_attempt >= interval
            return due and self._tick(week, now)
        except Exception as e:  # noqa: BLE001 - recorded and logged; the loop must survive
            self._record_error(e, now)
            return False

    def _tick(self, week: int, now: datetime) -> bool:
        if not api_routes.REFRESH_LOCK.acquire(blocking=False):
            log.info("live refresh skipped: a manual refresh is running")
            return False
        self._last_attempt = now  # failures wait a full interval: no tight retry loop
        try:
            sync_sleeper.sync_week(week)
            simulate.run(archive=False)
        finally:
            api_routes.REFRESH_LOCK.release()
        _clear_league_cache()
        self.runner.clear()
        self.state.last_ok_at = now.isoformat(timespec="seconds")
        self.state.last_error = self._last_error_text = None
        return True

    def _record_error(self, error: Exception, now: datetime) -> None:
        text = f"{type(error).__name__}: {error}"
        if text != self._last_error_text:
            log.exception("live refresh failed")  # once per distinct error, not every wake
        self._last_error_text = text
        message = f"{now.isoformat(timespec='seconds')} {text}"
        self.state.last_error = message
        self._last_attempt = now

    def _loop(self) -> None:
        while not self._stop.wait(POLL_SECONDS):
            self.step(datetime.now(UTC))

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="live-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
