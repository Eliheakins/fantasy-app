"""The /api/auth routes and the login gate.

The gate is on when data/auth.db holds an account, so a laptop with no accounts behaves as it always
did. FANTASY_AUTH=off turns it off; FANTASY_AUTH=required turns it on even before the first account,
which a public server needs. The session is a random token in an HttpOnly, SameSite=Lax cookie,
Secure unless AUTH_COOKIE_SECURE=0 (plain-http tests); the server keeps only its hash.
"""

import logging
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import cache
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import Field

from fantasy.api_envelope import fail, ok
from fantasy.api_models import Envelope, Row
from fantasy.auth import access, accounts, admin, my_leagues, policy
from fantasy.auth.ratelimit import FailureLimiter

log = logging.getLogger(__name__)
HOSTS_ENV = "API_ALLOWED_HOSTS"  # set on a public deployment: the site hostname
AUTH_MODES = frozenset({"on", "off", "required"})
COOKIE = "fantasy_session"
LOGIN_FAILURES = 5  # attempts per address and per email, per minute
LOGIN_WINDOW_S = 60.0
LOCAL_PEERS = frozenset({"127.0.0.1", "::1"})
# Every call to the Ask route reaches the paid model, so each account gets a few a minute, enough
# for a person typing and not for a script.
MODEL_ROUTE = "/api/stat/nlq/intent"
INTENT_PER_MINUTE = 20

limiter = FailureLimiter(limit=LOGIN_FAILURES, window_s=LOGIN_WINDOW_S)
intent_limiter = FailureLimiter(limit=INTENT_PER_MINUTE, window_s=60.0)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(Row):
    email: accounts.Email
    password: str = Field(max_length=256)


class Redemption(Row):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(max_length=256)


class Me(Row):
    email: str
    is_admin: bool
    sleeper_user_id: str | None


class SignedOut(Row):
    signed_out: bool


def cookie_secure() -> bool:
    return os.environ.get("AUTH_COOKIE_SECURE", "1") != "0"


def client_ip(request: Any) -> str:
    """The caller's address. Behind our own proxy the peer is local and the proxy appends the real
    address to X-Forwarded-For, so the last entry is the one to believe; another peer is itself."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if peer in LOCAL_PEERS and forwarded:
        return str(forwarded.split(",")[-1].strip())
    return str(peer)


def _me(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": account["email"],
        "is_admin": account["is_admin"],
        "sleeper_user_id": account["sleeper_user_id"],
    }


def _start_session(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=accounts.SESSION_DAYS * 86400,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=Envelope[Me])
def login(body: Credentials, request: Request, response: Response) -> Any:
    keys = (f"ip:{client_ip(request)}", f"email:{accounts.normalize_email(body.email)}")
    if not limiter.attempt(keys, time.monotonic()):  # counted before the slow scrypt check
        return fail("busy", "Too many attempts. Wait a minute and try again.", 429)
    with accounts.open_db(request.app.state.data_dir) as conn:
        account = accounts.login(conn, body.email, body.password)
        if account is None:
            return fail("invalid", "Wrong email or password.", 401)
        token = accounts.create_session(conn, account["id"], datetime.now(UTC))
    limiter.refund(keys[0])  # only wrong guesses count against the address
    limiter.clear(keys[1])
    _start_session(response, token)
    return ok(_me(account))


@router.post("/redeem", response_model=Envelope[Me])
def redeem(body: Redemption, request: Request, response: Response) -> Any:
    now = datetime.now(UTC)
    with accounts.open_db(request.app.state.data_dir) as conn:
        try:
            account = accounts.redeem_invite(conn, body.token, body.password, now)
        except accounts.InviteError as err:
            return fail("invalid", str(err), 400)
        token = accounts.create_session(conn, account["id"], now)
    _start_session(response, token)
    return ok(_me(account))


@router.post("/logout", response_model=Envelope[SignedOut])
def logout(request: Request, response: Response) -> Any:
    token = request.cookies.get(COOKIE)
    if token:
        with accounts.open_db(request.app.state.data_dir) as conn:
            accounts.end_session(conn, token)
    response.delete_cookie(COOKIE, path="/")
    return ok({"signed_out": True})


@router.post("/logout-everywhere", response_model=Envelope[SignedOut])
def logout_everywhere(request: Request, response: Response) -> Any:
    account = request.state.account  # None when the gate is off: there are no sessions to end
    if account is not None:
        with accounts.open_db(request.app.state.data_dir) as conn:
            accounts.end_all_sessions(conn, account["id"])
    response.delete_cookie(COOKIE, path="/")
    return ok({"signed_out": True})


@router.get("/me", response_model=Envelope[Me])
def me(request: Request) -> Any:
    account = request.state.account
    if account is None:  # the gate is off: a local run, where everyone is the admin
        return ok({"email": "local", "is_admin": True, "sleeper_user_id": None})
    return ok(_me(account))


def gate_mode() -> str:
    """off: no login at all. required: login even before the first account (a public server must not
    be open while it waits for its admin). on: login once an account exists. Anything else is an
    error: a typo must not quietly leave the site open."""
    mode = os.environ.get("FANTASY_AUTH", "on").strip().lower() or "on"
    if mode not in AUTH_MODES:
        raise ValueError(f"FANTASY_AUTH={mode!r} is not one of {', '.join(sorted(AUTH_MODES))}")
    return mode


@cache
def _warn_open_public_gate() -> None:
    """Once per process: the gate is open although this looks like a public deployment."""
    log.warning(
        "Login is NOT enforced: %s is set but data/auth.db has no accounts. Create the admin or "
        "set FANTASY_AUTH=required.",
        HOSTS_ENV,
    )


def _open_gate(mode: str) -> bool:
    """The gate's answer when there is no account to log in to."""
    if mode != "required" and os.environ.get(HOSTS_ENV, "").strip():
        _warn_open_public_gate()
    return mode == "required"


def _resolve(request: Request, data_dir: Any) -> tuple[bool, dict[str, Any] | None]:
    """Whether login is required, and who the cookie says is calling."""
    mode = gate_mode()
    if mode == "off":
        return False, None
    if not accounts.db_path(data_dir).exists():
        return _open_gate(mode), None
    with accounts.open_db(data_dir) as conn:
        if conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is None:
            return _open_gate(mode), None
        token = request.cookies.get(COOKIE)
        account = accounts.account_for_session(conn, token, datetime.now(UTC)) if token else None
        return True, account


def install(app: FastAPI) -> None:
    """Add the auth routes and the gate. Add it before the Host and CSRF checks so those run first
    (Starlette makes the last middleware added the outermost)."""
    log.info("Login gate mode: %s", gate_mode())  # a bad FANTASY_AUTH stops the app here
    app.include_router(router)
    app.include_router(admin.router)
    app.include_router(my_leagues.router)

    @app.middleware("http")
    async def require_login(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith("/api/"):  # the web app's files: no database to open
            request.state.account = None
            return await call_next(request)
        enforced, account = await run_in_threadpool(_resolve, request, request.app.state.data_dir)
        request.state.account = account
        if enforced:
            decision = policy.decide(request.method, request.url.path, account)
            if decision == "unauthorized":
                return fail("unauthorized", "Sign in to continue.", 401)
            if decision == "forbidden":
                return fail("forbidden", "Only the admin can do that.", 403)
            if (
                account is not None
                and request.method == "POST"
                and request.url.path == MODEL_ROUTE
                and not intent_limiter.attempt((f"ask:{account['id']}",), time.monotonic())
            ):
                return fail("busy", "Too many questions. Wait a minute and try again.", 429)
            league = access.LEAGUE_PATH.match(request.url.path)
            if league and account is not None:
                data_dir = request.app.state.data_dir
                if not await run_in_threadpool(access.can_see, account, league[1], data_dir):
                    return fail("no_data", "No such league.", 404)  # same answer as a missing one
        response: Response = await call_next(request)
        return response
