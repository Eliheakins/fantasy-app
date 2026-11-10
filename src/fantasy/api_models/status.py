"""Status page and refresh-queue models."""

from datetime import datetime
from typing import Literal

from fantasy.api_models.base import Row


class FreshnessRow(Row):
    source: str
    updated_at: datetime
    age_hours: float


class LiveRefreshData(Row):
    enabled: bool
    active: bool  # a game of the current week is on now
    last_ok_at: str | None  # ISO time of the last good live tick
    last_error: str | None
    interval_minutes: int


class RefreshRunRow(Row):
    stage: str
    finished_at: str
    status: Literal["ok", "failed"]
    error: str | None


class StatusData(Row):
    freshness: list[FreshnessRow]
    missing_layers: list[str]
    simulation_behind_inputs: str | None
    refresh_runs: list[RefreshRunRow]
    data_version: str
    live_refresh: LiveRefreshData


class RefreshData(Row):
    player_rows: int


class RefreshStatus(Row):
    state: Literal["idle", "queued", "running"]
    queued: int  # requests waiting for the next run
    last_finished_at: str | None  # when the newest stage of the last run finished
    last_run_failed: bool | None  # any stage of that run failed or was skipped
