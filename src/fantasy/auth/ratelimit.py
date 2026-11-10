"""Count login attempts per key (an address, an email) over a sliding window, in memory.

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
        self._swept_at = 0.0

    def _sweep(self, now: float) -> None:
        """Drop every expired key, at most once a window, so one-off attackers leave no trace."""
        if now - self._swept_at < self.window_s:
            return
        self._swept_at = now
        for key in list(self._failures):
            self._recent(key, now)

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
            self._sweep(now)
            self._failures[key] = [*self._recent(key, now), now]

    def attempt(self, keys: tuple[str, ...], now: float) -> bool:
        """Check and count in one step: False if any key is full, else every key is charged now.
        Counting before the slow check is what stops a burst of parallel guesses."""
        with self._lock:
            self._sweep(now)
            if any(len(self._recent(key, now)) >= self.limit for key in keys):
                return False
            for key in keys:
                self._failures[key] = [*self._failures.get(key, []), now]
            return True

    def refund(self, key: str) -> None:
        """Take back the newest count of `key` (the attempt turned out to be a success)."""
        with self._lock:
            remaining = self._failures.get(key, [])[:-1]
            if remaining:
                self._failures[key] = remaining
            else:
                self._failures.pop(key, None)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
