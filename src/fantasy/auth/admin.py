"""The admin's routes: who has an account, invite links, and the refresh. Every path under
/api/admin/ is closed to everyone else by `policy.decide`, so nothing here checks the caller."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from fantasy import refresh_queue
from fantasy.api_envelope import fail, guarded, ok
from fantasy.api_models import Envelope, RefreshStatus, Row
from fantasy.auth import accounts

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AccountRow(Row):
    id: int
    email: str
    is_admin: bool
    has_password: bool
    invite_pending: bool
    created_at: str


class InviteRequest(Row):
    email: accounts.Email


class InviteCreated(Row):
    email: str
    path: str  # the one-time link, without the site address: /invite/<token>
    valid_days: int


class RunRow(Row):
    run_id: str
    finished_at: str
    stages: int
    failed: int
    seconds: float


class RefreshAdmin(RefreshStatus):
    runs: list[RunRow]


class Removed(Row):
    email: str


@router.get("/accounts", response_model=Envelope[list[AccountRow]])
def list_accounts(request: Request) -> Any:
    def build() -> list[dict[str, Any]]:
        with accounts.open_db(request.app.state.data_dir) as conn:
            return [
                {k: v for k, v in row.items() if k != "sleeper_user_id"}
                for row in accounts.list_accounts(conn)
            ]

    return guarded(build)


@router.post("/invites", response_model=Envelope[InviteCreated])
def create_invite(body: InviteRequest, request: Request) -> Any:
    """A new single-use link. For an email that already has an account this replaces the old link
    and, once used, resets the password: it is also the way to recover a forgotten one."""
    with accounts.open_db(request.app.state.data_dir) as conn:
        token = accounts.create_invite(conn, body.email, datetime.now(UTC))
    return ok(
        {
            "email": accounts.normalize_email(body.email),
            "path": f"/invite/{token}",
            "valid_days": accounts.INVITE_DAYS,
        }
    )


@router.delete("/accounts/{account_id}", response_model=Envelope[Removed])
def remove_account(account_id: int, request: Request) -> Any:
    try:
        with accounts.open_db(request.app.state.data_dir) as conn:
            email = accounts.remove_account(conn, account_id)
    except LookupError as err:
        return fail("no_data", str(err), 404)
    except accounts.AccountError as err:
        return fail("invalid", str(err), 409)
    return ok({"email": email})


@router.get("/refresh", response_model=Envelope[RefreshAdmin])
def refresh_overview(request: Request) -> Any:
    data_dir = request.app.state.data_dir
    return guarded(
        lambda: {**refresh_queue.status(data_dir), "runs": refresh_queue.recent_runs(data_dir)}
    )


@router.post("/refresh", response_model=Envelope[RefreshStatus])
def refresh_now(request: Request) -> Any:
    """Queue a refresh; the server starts it within moments (or `make refresh` on a laptop)."""
    data_dir = request.app.state.data_dir
    refresh_queue.request_refresh("admin: refresh now", data_dir)
    return guarded(lambda: refresh_queue.status(data_dir))
