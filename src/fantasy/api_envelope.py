"""The JSON envelope {status, data, error, started_at} and the error mapping for routes."""

import logging
import math
from collections.abc import Callable
from typing import Any

import polars as pl
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    """Wrap `fn`'s result: FileNotFoundError is `no_data`, ValueError `invalid` (both HTTP 200),
    anything else `server` (HTTP 500)."""
    try:
        return ok(fn())
    except FileNotFoundError:
        log.warning("table missing", exc_info=True)
        return fail("no_data", NO_DATA_MESSAGE)
    except ValueError as err:
        return fail("invalid", str(err))
    except Exception:  # last resort: never leak the text of an unexpected error
        log.exception("unexpected error")
        return fail("server", SERVER_MESSAGE, 500)


def _validation_message(err: RequestValidationError) -> str:
    """The first problem as "field: message"; the field is the loc without its query/body prefix."""
    first = err.errors()[0]
    parts = first["loc"][1:]
    field = "" if any(isinstance(p, int) for p in parts) else ".".join(map(str, parts))
    return f"{field}: {first['msg']}" if field else str(first["msg"])


def register_error_handlers(app: FastAPI) -> None:
    """Make the envelope the one error shape: validation, response drift and HTTP errors."""

    @app.exception_handler(RequestValidationError)
    async def on_invalid_request(_: Request, err: RequestValidationError) -> JSONResponse:
        return fail("invalid", _validation_message(err), 422)

    @app.exception_handler(ResponseValidationError)
    async def on_response_drift(_: Request, err: ResponseValidationError) -> JSONResponse:
        log.error("response failed its model", exc_info=err)
        return fail("server", SERVER_MESSAGE, 500)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(_: Request, err: StarletteHTTPException) -> JSONResponse:
        code = "server" if err.status_code >= 500 else "invalid"
        response = fail(code, str(err.detail), err.status_code)
        response.headers.update(err.headers or {})  # e.g. a 405's Allow
        return response

    @app.exception_handler(Exception)
    async def on_unexpected(_: Request, err: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=err)
        return fail("server", SERVER_MESSAGE, 500)
