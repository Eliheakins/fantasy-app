"""Thin client for Sleeper's read-only API. Stay well under 1,000 calls per minute."""

import time
from typing import Any

import httpx

BASE = "https://api.sleeper.app/v1"
PAUSE_SECONDS = 0.1  # about 600 calls a minute at most
RETRIES = 3


def fetch(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{BASE}{path}"
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            resp = httpx.get(url, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(PAUSE_SECONDS)
            return resp.json()
        except httpx.HTTPError as err:
            last = err
            time.sleep(2**attempt)
    raise RuntimeError(f"Sleeper request failed after {RETRIES} tries: {url}") from last
