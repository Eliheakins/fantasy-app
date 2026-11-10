"""Count failed logins per key (an address, an email) over a sliding window, in memory.

One process serves the site, so a plain dictionary is enough; a restart forgets the counts, which
only helps an attacker once per restart.
"""

import threading


class FailureLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_s]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)  # keys of finished attackers do not pile up
        return recent

    def blocked(self, key: str, now: float) -> bool:
        with self._lock:
            return len(self._recent(key, now)) >= self.limit

    def record(self, key: str, now: float) -> None:
        with self._lock:
            self._failures[key] = [*self._recent(key, now), now]

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
