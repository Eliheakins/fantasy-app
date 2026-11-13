import time
from typing import Any

import httpx2
import pytest

from fantasy.sources import sleeper


def _respond(monkeypatch: pytest.MonkeyPatch, *outcomes: int | Exception) -> list[str]:
    """Each httpx2.get call takes the next outcome: a status code or an exception to raise."""
    calls: list[str] = []
    queue = list(outcomes)

    def get(url: str, **kwargs: Any) -> httpx2.Response:
        calls.append(url)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx2.Response(outcome, json=[1], request=httpx2.Request("GET", url))

    monkeypatch.setattr(httpx2, "get", get)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    return calls


def test_fetch_retries_a_rate_limit_then_returns_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _respond(monkeypatch, 429, 200)
    assert sleeper.fetch("/state/nfl") == [1]
    assert len(calls) == 2


def test_fetch_gives_up_at_once_on_a_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _respond(monkeypatch, 404)
    with pytest.raises(sleeper.SleeperError, match="rejected"):
        sleeper.fetch("/league/x")
    assert len(calls) == 1


def test_fetch_raises_sleeper_error_after_every_try_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _respond(monkeypatch, 503, httpx2.ConnectError("down"), 500)
    with pytest.raises(sleeper.SleeperError, match="after 3 tries"):
        sleeper.fetch("/state/nfl")
    assert len(calls) == sleeper.RETRIES
