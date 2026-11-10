"""The leagues people added by Sleeper username: which ones to sync, who may see each, and how the
last sync went.

One row per league however many people added it (two league-mates share it, so it is fetched and
simulated once). `account_leagues` says who may see it. The owner's own leagues are not here: they
come from config.toml.
"""

import sqlite3
from datetime import datetime
from typing import Any

from fantasy.auth import accounts

MAX_ADDED_LEAGUES = 2
QUEUED, READY, ERROR = "queued", "ready", "error"


class LeagueLimit(ValueError):
    """The account already has as many added leagues as it may; the message is safe to show."""


def key_for(league_id: str) -> str:
    """The league's key in the data tables. The prefix keeps it clear of config.toml's names."""
    return f"sl-{league_id}"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "league_id": row["league_id"],
        "league_key": row["league_key"],
        "name": row["name"],
        "status": row["status"],
        "error": row["error"],
    }


def mine(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """The account's leagues, each with the roster it picked (None: added before teams were)."""
    rows = conn.execute(
        "SELECT r.*, g.roster_id FROM league_registry r"
        " JOIN account_leagues g ON g.league_id = r.league_id"
        " WHERE g.account_id = ? ORDER BY g.added_at, r.league_id",
        (account_id,),
    ).fetchall()
    return [{**_row(row), "roster_id": row["roster_id"]} for row in rows]


def chosen_rosters(conn: sqlite3.Connection, account_id: int) -> dict[str, int]:
    """league_id -> the roster the account picked as its own, where it picked one."""
    rows = conn.execute(
        "SELECT league_id, roster_id FROM account_leagues"
        " WHERE account_id = ? AND roster_id IS NOT NULL",
        (account_id,),
    ).fetchall()
    return {row["league_id"]: int(row["roster_id"]) for row in rows}


def set_team(conn: sqlite3.Connection, account_id: int, league_id: str, roster_id: int) -> bool:
    """Make `roster_id` the account's team in the league. Returns whether the account has it."""
    with conn:
        changed = conn.execute(
            "UPDATE account_leagues SET roster_id = ? WHERE account_id = ? AND league_id = ?",
            (roster_id, account_id, league_id),
        ).rowcount
    return changed == 1


def registered(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every league to sync, whatever its status: an errored one is tried again each refresh."""
    rows = conn.execute("SELECT * FROM league_registry ORDER BY added_at, league_id").fetchall()
    return [_row(row) for row in rows]


def add(
    conn: sqlite3.Connection,
    account_id: int,
    league_id: str,
    name: str,
    now: datetime,
    roster_id: int | None = None,
) -> dict[str, Any]:
    """Register the league (if nobody has) and let the account see it, with `roster_id` as its
    team. Safe to repeat; a repeat with a roster changes the team."""
    held = {row["league_id"] for row in mine(conn, account_id)}
    if league_id not in held and len(held) >= MAX_ADDED_LEAGUES:
        raise LeagueLimit(
            f"You can add up to {MAX_ADDED_LEAGUES} leagues. Remove one to add another."
        )
    stamp = accounts.stamp(now)
    with conn:
        conn.execute(
            "INSERT INTO league_registry"
            " (league_id, league_key, name, status, added_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(league_id) DO NOTHING",
            (league_id, key_for(league_id), name, QUEUED, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO account_leagues (account_id, league_id, added_at, roster_id)"
            " VALUES (?, ?, ?, ?) ON CONFLICT DO UPDATE"
            " SET roster_id = coalesce(excluded.roster_id, roster_id)",
            (account_id, league_id, stamp, roster_id),
        )
    return next(row for row in mine(conn, account_id) if row["league_id"] == league_id)


def release(conn: sqlite3.Connection, account_id: int, league_id: str) -> bool:
    """Take the league away from the account; when nobody has it any more it leaves the sync.
    Returns whether the account had it."""
    with conn:
        removed = conn.execute(
            "DELETE FROM account_leagues WHERE account_id = ? AND league_id = ?",
            (account_id, league_id),
        ).rowcount
        accounts.forget_unwatched_leagues(conn)
    return removed == 1


def mark(conn: sqlite3.Connection, league_id: str, error: str | None, now: datetime) -> None:
    """Record how the last sync of the league went: ready, or the reason it was not."""
    with conn:
        conn.execute(
            "UPDATE league_registry SET status = ?, error = ?, updated_at = ? WHERE league_id = ?",
            (ERROR if error else READY, error, accounts.stamp(now), league_id),
        )
