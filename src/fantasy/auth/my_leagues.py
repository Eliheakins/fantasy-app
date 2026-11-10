"""A signed-in person adds their own Sleeper leagues by Sleeper username.

Sleeper cannot prove who someone is, so the checks are the ones that can be made: the league must
be in that user's current-season list, one team in it must belong to that user, and an account
stays tied to the first Sleeper user it used. League data is public on Sleeper, so nothing secret is
exposed; the account link only decides whose list a league appears in. Adding a league queues a
refresh, and the next run reads it (see fantasy/refresh_queue and stages/sync_sleeper).
"""

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field

from fantasy import refresh_queue
from fantasy.api_envelope import fail, guarded, ok
from fantasy.api_models import Envelope, Row
from fantasy.auth import accounts, leagues
from fantasy.auth.ratelimit import FailureLimiter
from fantasy.config import load_config
from fantasy.sim.season import format_problem
from fantasy.sources.sleeper import SleeperError, fetch

USERNAME_PATTERN = r"^[A-Za-z0-9_]{1,40}$"  # Sleeper usernames; nothing that could alter the url
LOOKUPS_PER_MINUTE = 10

lookup_limiter = FailureLimiter(limit=LOOKUPS_PER_MINUTE, window_s=60.0)
router = APIRouter(prefix="/api/me", tags=["me"])


class LookupRequest(Row):
    username: str = Field(pattern=USERNAME_PATTERN)


class AddRequest(Row):
    username: str = Field(pattern=USERNAME_PATTERN)
    league_id: str = Field(pattern=r"^[0-9]{1,30}$")


class SleeperLeague(Row):
    league_id: str
    name: str
    num_teams: int | None
    added: bool  # already one of this account's leagues
    problem: str | None  # why the app cannot model it (so it cannot be added), else null


class Lookup(Row):
    username: str
    display_name: str
    leagues: list[SleeperLeague]


class MyLeague(Row):
    league_id: str
    league_key: str
    name: str
    status: str  # queued (waiting for a refresh), ready, or error
    error: str | None


class Removed(Row):
    league_id: str


class SleeperUnreachable(Exception):
    """Sleeper did not answer; the message is safe to show."""


def _sleeper(path: str) -> Any:
    try:
        return fetch(path)
    except SleeperError as err:
        raise SleeperUnreachable("Sleeper did not answer. Try again in a minute.") from err


def _user(username: str) -> dict[str, Any] | None:
    found = _sleeper(f"/user/{username}")
    return found if isinstance(found, dict) and found.get("user_id") else None


def _their_leagues(user_id: str) -> list[dict[str, Any]]:
    found = _sleeper(f"/user/{user_id}/leagues/nfl/{load_config().season}")
    return [lg for lg in found if isinstance(lg, dict)] if isinstance(found, list) else []


def _problem(lg: dict[str, Any]) -> str | None:
    """Why the season simulation cannot model this league, from Sleeper's own settings."""
    settings = lg.get("settings") or {}
    return format_problem(
        settings.get("num_teams"), settings.get("playoff_teams"), settings.get("playoff_week_start")
    )


def _account(request: Request) -> dict[str, Any] | None:
    account: dict[str, Any] | None = request.state.account
    return account


def no_account() -> Any:
    """These routes belong to a signed-in account; on a laptop with no accounts there is none."""
    return fail("unauthorized", "Sign in to add leagues.", 401)


NO_USER = "No Sleeper user has that name."


@router.post("/sleeper/lookup", response_model=Envelope[Lookup])
def lookup(body: LookupRequest, request: Request) -> Any:
    account = _account(request)
    if account is None:
        return no_account()
    key = f"lookup:{account['id']}"
    now = time.monotonic()
    if lookup_limiter.blocked(key, now):
        return fail("busy", "Too many lookups. Wait a minute and try again.", 429)
    lookup_limiter.record(key, now)
    try:
        user = _user(body.username)
        if user is None:
            return fail("no_data", NO_USER, 404)
        theirs = _their_leagues(str(user["user_id"]))
    except SleeperUnreachable as err:
        return fail("server", str(err), 502)
    with accounts.open_db(request.app.state.data_dir) as conn:
        added = {row["league_id"] for row in leagues.mine(conn, account["id"])}
    return ok(
        {
            "username": body.username,
            "display_name": str(user.get("display_name") or body.username),
            "leagues": [
                {
                    "league_id": str(lg["league_id"]),
                    "name": str(lg.get("name") or lg["league_id"]),
                    "num_teams": lg.get("total_rosters"),
                    "added": str(lg["league_id"]) in added,
                    "problem": _problem(lg),
                }
                for lg in theirs
            ],
        }
    )


@router.post("/leagues", response_model=Envelope[MyLeague])
def add_league(body: AddRequest, request: Request) -> Any:
    account = _account(request)
    if account is None:
        return no_account()
    try:
        user = _user(body.username)
        if user is None:
            return fail("no_data", NO_USER, 404)
        user_id = str(user["user_id"])
        theirs = {str(lg["league_id"]): lg for lg in _their_leagues(user_id)}
        if body.league_id not in theirs:
            return fail("no_data", "That league is not one of that user's current leagues.", 404)
        rosters = _sleeper(f"/league/{body.league_id}/rosters")
    except SleeperUnreachable as err:
        return fail("server", str(err), 502)
    problem = _problem(theirs[body.league_id])
    if problem:
        return fail("invalid", f"{problem} It cannot be added.", 409)
    if not any(isinstance(r, dict) and r.get("owner_id") == user_id for r in rosters or []):
        return fail("invalid", "No team in that league belongs to that Sleeper user.", 409)
    linked = account["sleeper_user_id"]
    if linked and linked != user_id:
        return fail("invalid", "This account is already linked to a different Sleeper user.", 409)
    name = str(theirs[body.league_id].get("name") or body.league_id)
    with accounts.open_db(request.app.state.data_dir) as conn:
        try:
            row = leagues.add(conn, account["id"], body.league_id, name, datetime.now(UTC))
        except leagues.LeagueLimit as err:
            return fail("invalid", str(err), 409)
        if not linked:
            accounts.set_sleeper_user(conn, account["id"], user_id)
    refresh_queue.request_refresh(f"league added: {body.league_id}", request.app.state.data_dir)
    return ok(row)


@router.get("/leagues", response_model=Envelope[list[MyLeague]])
def my_leagues(request: Request) -> Any:
    account = _account(request)
    if account is None:
        return no_account()

    def build() -> list[dict[str, Any]]:
        with accounts.open_db(request.app.state.data_dir) as conn:
            return leagues.mine(conn, account["id"])

    return guarded(build)


@router.delete("/leagues/{league_id}", response_model=Envelope[Removed])
def remove_league(league_id: str, request: Request) -> Any:
    account = _account(request)
    if account is None:
        return no_account()
    with accounts.open_db(request.app.state.data_dir) as conn:
        if not leagues.release(conn, account["id"], league_id):
            return fail("no_data", "You have not added that league.", 404)
    return ok({"league_id": league_id})
