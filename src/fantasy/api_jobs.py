"""Single-flight runner for long simulations: one Future per (endpoint, args, data version)."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

MAX_ACTIVE_JOBS = 8
MAX_ACTIVE_PER_OWNER = 4  # so one friend cannot take every slot
MAX_REMEMBERED_JOBS = 64
JobKey = tuple[str, tuple[Any, ...], str]  # endpoint, args, data_version


class Busy(Exception):
    """Too many jobs are queued or running."""


@dataclass(frozen=True)
class Job:
    future: "Future[Any]"
    started_at: str
    owner: int | None = None  # the account that started it; None for the admin and a local run


class JobRunner:
    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[JobKey, Job] = {}
        self._lock = Lock()

    def submit(self, key: JobKey, fn: Callable[[], Any], owner: int | None = None) -> Job:
        """The job for `key`: the existing one, or a new one started now for `owner`. Finished jobs
        from an older data version are dropped."""
        with self._lock:
            self._jobs = {
                k: j for k, j in self._jobs.items() if k[2] == key[2] or not j.future.done()
            }
            if key not in self._jobs:
                active = [j for j in self._jobs.values() if not j.future.done()]
                if len(active) >= MAX_ACTIVE_JOBS:
                    raise Busy
                if (
                    owner is not None
                    and sum(j.owner == owner for j in active) >= MAX_ACTIVE_PER_OWNER
                ):
                    raise Busy("You have several long jobs running. Wait for one to finish.")
                self._evict_oldest_finished()
                started = datetime.now(UTC).isoformat(timespec="seconds")
                self._jobs[key] = Job(self._pool.submit(fn), started, owner)
            return self._jobs[key]

    def _evict_oldest_finished(self) -> None:
        """Make room for one more job; the dict keeps insertion order, oldest first."""
        finished = [k for k, j in self._jobs.items() if j.future.done()]
        for k in finished[: max(0, len(self._jobs) - MAX_REMEMBERED_JOBS + 1)]:
            del self._jobs[k]

    def forget(self, key: JobKey) -> None:
        """Drop a job (used after a failure is reported, so the next request retries)."""
        with self._lock:
            self._jobs.pop(key, None)

    def clear(self) -> None:
        """Drop finished jobs; running ones stay so they are never run twice at once."""
        with self._lock:
            self._jobs = {k: j for k, j in self._jobs.items() if not j.future.done()}

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
