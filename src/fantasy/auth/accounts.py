"""Accounts, invite links and sessions, in the SQLite file data/auth.db.

Tokens (invite links, session cookies) are random and stored only as SHA-256 hashes, so a copy of
the database cannot be used to sign in. An invite link is single-use and sets the password; issuing
a new link for an existing account cancels the old one and doubles as a password reset.
"""

import hashlib
import logging
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from pydantic import StringConstraints

from fantasy import store
from fantasy.auth import passwords

log = logging.getLogger(__name__)
SESSION_DAYS = 30
EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$"  # one @, no spaces, a dot after it
INVITE_DAYS = 7
# an email as typed: surrounding spaces (a pasted line) are dropped before the shape is checked
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254, pattern=EMAIL_PATTERN)
]
DB_NAME = "auth.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    sleeper_user_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS account_leagues (
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    league_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    roster_id INTEGER,
    PRIMARY KEY (account_id, league_id)
);
CREATE TABLE IF NOT EXISTS league_registry (
    league_id TEXT PRIMARY KEY,
    league_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    added_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class InviteError(ValueError):
    """The invite link or the chosen password cannot be used; the message is safe to show."""


def db_path(data_dir: Path | None = None) -> Path:
    return store.resolve(data_dir) / DB_NAME


def connect(data_dir: Path | None = None) -> sqlite3.Connection:
    path = db_path(data_dir)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)  # the mode applies only if created
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_leagues)")}
    if "roster_id" not in columns:  # a database made before teams were chosen
        conn.execute("ALTER TABLE account_leagues ADD COLUMN roster_id INTEGER")
    for file in (path, *path.parent.glob(f"{path.name}-*")):  # -wal and -shm hold the same data
        try:
            file.chmod(0o600)
        except PermissionError:  # another user's file (a CLI run as root): serve, but say so
            log.warning("cannot make %s owner-only; it belongs to another user", file)
    return conn


@contextmanager
def open_db(data_dir: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(data_dir)
    try:
        yield conn
    finally:
        conn.close()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "is_admin": bool(row["is_admin"]),
        "sleeper_user_id": row["sleeper_user_id"],
    }


def create_admin(conn: sqlite3.Connection, email: str, password: str) -> int:
    """Create the admin, or reset the password (and sign out everywhere) if the email exists.
    Returns the account id."""
    problem = passwords.check_length(password)
    if problem:
        raise ValueError(problem)
    hashed = passwords.hash_password(password)
    with conn:
        admin_id: int = conn.execute(
            "INSERT INTO accounts (email, password_hash, is_admin, created_at) VALUES (?, ?, 1, ?)"
            " ON CONFLICT(email) DO UPDATE"
            " SET password_hash = excluded.password_hash, is_admin = 1 RETURNING id",
            (normalize_email(email), hashed, stamp(datetime.now(UTC))),
        ).fetchone()[0]
        conn.execute("DELETE FROM sessions WHERE account_id = ?", (admin_id,))
    return admin_id


def create_invite(conn: sqlite3.Connection, email: str, now: datetime) -> str:
    """A new single-use link for `email` (the account is created without a password if new).
    Returns the token, shown once; only its hash is kept."""
    address = normalize_email(email)
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO accounts (email, created_at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
            (address, stamp(now)),
        )
        account_id = conn.execute("SELECT id FROM accounts WHERE email = ?", (address,)).fetchone()[
            0
        ]
        conn.execute("DELETE FROM invites WHERE account_id = ? AND used_at IS NULL", (account_id,))
        conn.execute(
            "INSERT INTO invites (account_id, token_hash, expires_at, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                account_id,
                _hash_token(token),
                stamp(now + timedelta(days=INVITE_DAYS)),
                stamp(now),
            ),
        )
    return token


def redeem_invite(
    conn: sqlite3.Connection, token: str, password: str, now: datetime
) -> dict[str, Any]:
    """Use an invite link to set the password. Raises InviteError with a message fit to show."""
    invite = conn.execute(
        "SELECT id, account_id, expires_at, used_at FROM invites WHERE token_hash = ?",
        (_hash_token(token),),
    ).fetchone()
    if invite is None:
        raise InviteError("This invite link is not valid.")
    if invite["used_at"] is not None:
        raise InviteError("This invite link was already used.")
    if invite["expires_at"] < stamp(now):
        raise InviteError("This invite link has expired. Ask for a new one.")
    problem = passwords.check_length(password)
    if problem:
        raise InviteError(problem)
    hashed = passwords.hash_password(password)
    with conn:
        claimed = conn.execute(
            "UPDATE invites SET used_at = ? WHERE id = ? AND used_at IS NULL",
            (stamp(now), invite["id"]),
        ).rowcount
        if claimed != 1:  # someone else redeemed it between the check and now
            raise InviteError("This invite link was already used.")
        conn.execute(
            "UPDATE accounts SET password_hash = ? WHERE id = ?", (hashed, invite["account_id"])
        )
        conn.execute("DELETE FROM sessions WHERE account_id = ?", (invite["account_id"],))
    return _public(
        conn.execute("SELECT * FROM accounts WHERE id = ?", (invite["account_id"],)).fetchone()
    )


def login(conn: sqlite3.Connection, email: str, password: str) -> dict[str, Any] | None:
    """The account for a right email and password, else None (an unknown email costs a hash too)."""
    row = conn.execute(
        "SELECT * FROM accounts WHERE email = ?", (normalize_email(email),)
    ).fetchone()
    stored = row["password_hash"] if row is not None else None
    matches = passwords.verify_password(password, stored or passwords.dummy_hash())
    return _public(row) if row is not None and stored and matches else None


def create_session(conn: sqlite3.Connection, account_id: int, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (stamp(now),))
        conn.execute(
            "INSERT INTO sessions (account_id, token_hash, expires_at, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                account_id,
                _hash_token(token),
                stamp(now + timedelta(days=SESSION_DAYS)),
                stamp(now),
            ),
        )
    return token


def account_for_session(
    conn: sqlite3.Connection, token: str, now: datetime
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT a.* FROM sessions s JOIN accounts a ON a.id = s.account_id"
        " WHERE s.token_hash = ? AND s.expires_at > ? AND a.password_hash IS NOT NULL",
        (_hash_token(token), stamp(now)),
    ).fetchone()
    return _public(row) if row is not None else None


def end_session(conn: sqlite3.Connection, token: str) -> None:
    with conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


def end_all_sessions(conn: sqlite3.Connection, account_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM sessions WHERE account_id = ?", (account_id,))


def list_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every account for the admin panel, without any hash."""
    rows = conn.execute(
        "SELECT a.*, EXISTS (SELECT 1 FROM invites i WHERE i.account_id = a.id"
        " AND i.used_at IS NULL) AS pending FROM accounts a ORDER BY a.id"
    ).fetchall()
    return [
        {
            **_public(row),
            "has_password": row["password_hash"] is not None,
            "invite_pending": bool(row["pending"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def granted_league_ids(conn: sqlite3.Connection, account_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT league_id FROM account_leagues WHERE account_id = ?", (account_id,)
    ).fetchall()
    return {row["league_id"] for row in rows}


def set_sleeper_user(conn: sqlite3.Connection, account_id: int, sleeper_user_id: str) -> None:
    with conn:
        conn.execute(
            "UPDATE accounts SET sleeper_user_id = ? WHERE id = ?", (sleeper_user_id, account_id)
        )


class AccountError(ValueError):
    """The account cannot be changed that way; the message is safe to show."""


def remove_account(conn: sqlite3.Connection, account_id: int) -> str:
    """Delete a non-admin account with its invites, sessions and grants; returns its email."""
    row = conn.execute(
        "SELECT email, is_admin FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise LookupError("No such account.")
    if row["is_admin"]:
        raise AccountError("The admin account cannot be removed.")
    with conn:
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))  # the rest cascades
        forget_unwatched_leagues(conn)
    return str(row["email"])


def forget_unwatched_leagues(conn: sqlite3.Connection) -> None:
    """Drop registry rows nobody may see any more, so they stop being synced. Call inside a
    transaction."""
    conn.execute(
        "DELETE FROM league_registry WHERE league_id NOT IN (SELECT league_id FROM account_leagues)"
    )
