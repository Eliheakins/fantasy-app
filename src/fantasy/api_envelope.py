"""The JSON envelope {status, data, error, started_at} and the error mapping for routes."""

import logging
import math
from collections.abc import Callable
from typing import Any

import polars as pl
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)
NO_DATA_MESSAGE = "No data yet. Run `make refresh`, then reload."
SERVER_MESSAGE = "Something went wrong on the server. See the server log."


def clean(value: Any) -> Any:
    """Replace NaN and infinity with None, at any depth (JSON has neither)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean(v) for v in value]
    return value


def rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    """A frame as a list of row dicts, NaN as null."""
    return clean(frame.fill_nan(None).to_dicts())


def ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "data": clean(data), "error": None, "started_at": None}


def fail(code: str, message: str, status_code: int = 200) -> JSONResponse:
    """An error envelope, HTTP 200 by default: the UI reads `status`, the transport worked."""
    body = {"status": "error", "data": None, "error": {"code": code, "message": message}}
    return JSONResponse({**body, "started_at": None}, status_code=status_code)


def running(started_at: str) -> JSONResponse:
    body = {"status": "running", "data": None, "error": None, "started_at": started_at}
    return JSONResponse(body, status_code=202)


def guarded(fn: Callable[[], Any]) -> Any:
    """Wrap `fn`'s result; FileNotFoundError is `no_data`, ValueError `invalid`, else `server`."""
    try:
        return ok(fn())
    except FileNotFoundError:
        log.warning("table missing", exc_info=True)
        return fail("no_data", NO_DATA_MESSAGE)
    except ValueError as err:
        return fail("invalid", str(err))
    except Exception:  # last resort: never leak the text of an unexpected error
        log.exception("unexpected error")
        return fail("server", SERVER_MESSAGE)
