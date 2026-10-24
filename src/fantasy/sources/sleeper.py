"""Thin client for Sleeper's read-only API. Stay well under 1,000 calls per minute."""

import time
from typing import Any

import httpx

BASE = "https://api.sleeper.app/v1"
PAUSE_SECONDS = 0.1  # about 600 calls a minute at most
RETRIES = 3


RETRY_CLIENT_ERRORS = frozenset({408, 429})


def fetch(path: str, params: dict[str, Any] | None = None, base: str = BASE) -> Any:
    url = f"{base}{path}"
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            resp = httpx.get(url, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(PAUSE_SECONDS)
            return resp.json()
        except httpx.HTTPStatusError as err:
            status = err.response.status_code
            if status < 500 and status not in RETRY_CLIENT_ERRORS:
                # a client error will not fix itself, except rate limits and timeouts
                raise RuntimeError(f"Sleeper rejected the request: {url}") from err
            last = err
        except (httpx.HTTPError, ValueError) as err:  # network trouble or an undecodable body
            last = err
        if attempt < RETRIES - 1:
            time.sleep(2**attempt)
    raise RuntimeError(f"Sleeper request failed after {RETRIES} tries: {url}") from last
