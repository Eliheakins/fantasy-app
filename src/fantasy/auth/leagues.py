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
    rows = conn.execute(
        "SELECT r.* FROM league_registry r JOIN account_leagues g ON g.league_id = r.league_id"
        " WHERE g.account_id = ? ORDER BY g.added_at, r.league_id",
        (account_id,),
    ).fetchall()
    return [_row(row) for row in rows]


def registered(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every league to sync, whatever its status: an errored one is tried again each refresh."""
    rows = conn.execute("SELECT * FROM league_registry ORDER BY added_at, league_id").fetchall()
    return [_row(row) for row in rows]


def add(
    conn: sqlite3.Connection, account_id: int, league_id: str, name: str, now: datetime
) -> dict[str, Any]:
    """Register the league (if nobody has) and let the account see it. Safe to repeat."""
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
            "INSERT INTO account_leagues (account_id, league_id, added_at) VALUES (?, ?, ?)"
            " ON CONFLICT DO NOTHING",
            (account_id, league_id, stamp),
        )
    row = conn.execute("SELECT * FROM league_registry WHERE league_id = ?", (league_id,)).fetchone()
    return _row(row)


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
