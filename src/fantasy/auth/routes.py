"""The /api/auth routes and the login gate.

The gate is on when data/auth.db holds an account, so a laptop with no accounts behaves as it always
did. FANTASY_AUTH=off turns it off; FANTASY_AUTH=required turns it on even before the first account,
which a public server needs. The session is a random token in an HttpOnly, SameSite=Lax cookie,
Secure unless AUTH_COOKIE_SECURE=0 (plain-http tests); the server keeps only its hash.
"""

import os
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import Field

from fantasy.api_envelope import fail, ok
from fantasy.api_models import Envelope, Row
from fantasy.auth import access, accounts, admin, my_leagues, policy
from fantasy.auth.ratelimit import FailureLimiter

COOKIE = "fantasy_session"
LOGIN_FAILURES = 5  # per address and per email, per minute
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
    now = time.monotonic()
    keys = (f"ip:{client_ip(request)}", f"email:{accounts.normalize_email(body.email)}")
    if any(limiter.blocked(key, now) for key in keys):
        return fail("busy", "Too many attempts. Wait a minute and try again.", 429)
    with accounts.open_db(request.app.state.data_dir) as conn:
        account = accounts.login(conn, body.email, body.password)
        if account is None:
            for key in keys:
                limiter.record(key, now)
            return fail("invalid", "Wrong email or password.", 401)
        token = accounts.create_session(conn, account["id"], datetime.now(UTC))
    limiter.clear(keys[1])  # the address keeps its count: signing in elsewhere must not reset it
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


@router.get("/me", response_model=Envelope[Me])
def me(request: Request) -> Any:
    account = request.state.account
    if account is None:  # the gate is off: a local run, where everyone is the admin
        return ok({"email": "local", "is_admin": True, "sleeper_user_id": None})
    return ok(_me(account))


def _gate_mode() -> str:
    """off: no login at all. required: login even before the first account (a public server must not
    be open while it waits for its admin). Anything else: login once an account exists."""
    mode = os.environ.get("FANTASY_AUTH", "on").strip().lower()
    return mode if mode in {"off", "required"} else "on"


def _resolve(request: Request, data_dir: Any) -> tuple[bool, dict[str, Any] | None]:
    """Whether login is required, and who the cookie says is calling."""
    mode = _gate_mode()
    if mode == "off":
        return False, None
    if not accounts.db_path(data_dir).exists():
        return mode == "required", None
    with accounts.open_db(data_dir) as conn:
        if conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is None:
            return mode == "required", None
        token = request.cookies.get(COOKIE)
        account = accounts.account_for_session(conn, token, datetime.now(UTC)) if token else None
        return True, account


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.include_router(admin.router)
    app.include_router(my_leagues.router)

    @app.middleware("http")
    async def require_login(request: Request, call_next: Any) -> Response:
        enforced, account = await run_in_threadpool(_resolve, request, request.app.state.data_dir)
        request.state.account = account
        if enforced:
            decision = policy.decide(request.method, request.url.path, account)
            if decision == "unauthorized":
                return fail("unauthorized", "Sign in to continue.", 401)
            if decision == "forbidden":
                return fail("forbidden", "Only the admin can do that.", 403)
            if account is not None and request.method == "POST" and request.url.path == MODEL_ROUTE:
                key, now = f"ask:{account['id']}", time.monotonic()
                if intent_limiter.blocked(key, now):
                    return fail("busy", "Too many questions. Wait a minute and try again.", 429)
                intent_limiter.record(key, now)
            league = access.LEAGUE_PATH.match(request.url.path)
            if league and account is not None:
                data_dir = request.app.state.data_dir
                if not await run_in_threadpool(access.can_see, account, league[1], data_dir):
                    return fail("no_data", "No such league.", 404)  # same answer as a missing one
        response: Response = await call_next(request)
        return response
