"""FastAPI app over `data_api`: `python -m fantasy.api` serves it, `--openapi` prints the schema."""

import json
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fantasy.api_envelope import clean as clean
from fantasy.api_envelope import fail
from fantasy.api_envelope import rows as rows
from fantasy.api_jobs import JobRunner
from fantasy.api_routes import router
from fantasy.config import ROOT
from fantasy.live_refresh import LiveRefresher

WEB_DIST = ROOT / "web" / "dist"
LOCAL_HOSTS = ("localhost", "127.0.0.1")
HOSTS_ENV = "API_ALLOWED_HOSTS"  # comma separated, e.g. the tailnet name
CSRF_HEADER, CSRF_VALUE = "x-requested-with", "fantasy-app"  # a browser cannot add it cross-site
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
HOST, PORT = "127.0.0.1", 8000


def allowed_hosts() -> list[str]:
    extra = [h.strip() for h in os.environ.get(HOSTS_ENV, "").split(",") if h.strip()]
    return [*LOCAL_HOSTS, *extra]


def forbidden(request: Request, hosts: list[str]) -> str | None:
    """Why a request is refused, or None. Blocks cross-site POSTs to localhost."""
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).hostname not in hosts:
        return "Origin not allowed."
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        return "Missing X-Requested-With header."
    return None


def create_app(web_dist: Path | None = None) -> FastAPI:
    dist = WEB_DIST if web_dist is None else web_dist
    runner = JobRunner(max_workers=2)
    live = LiveRefresher(runner)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        live.start()
        try:
            yield
        finally:
            live.stop()
            runner.shutdown()

    app = FastAPI(title="Fantasy API", version="1", lifespan=lifespan)
    app.state.runner = runner
    app.state.live = live
    hosts = allowed_hosts()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def guard_cross_site(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        reason = forbidden(request, hosts)
        return fail("invalid", reason, 403) if reason else await call_next(request)

    app.include_router(router)
    if dist.is_dir():  # mounted last so /api wins; absent until `web/` is built
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


def main(argv: list[str]) -> None:
    if "--openapi" in argv:
        print(json.dumps(create_app().openapi(), indent=2))
        return
    import uvicorn

    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main(sys.argv[1:])
