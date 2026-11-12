"""Helpers for API tests that sign in: cheap hashing, a CSRF-ready client, signed-in accounts."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from store_fixture import LID

from fantasy import api
from fantasy.auth import accounts, passwords

CSRF_HEADER = {"X-Requested-With": "fantasy-app"}
GOOD = "a long enough password"


def isolate_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cheap hashing, plain-http cookies, no live refresh thread, auth mode from the data folder."""
    monkeypatch.setattr(passwords, "COST_N", 2**10)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")  # the test client speaks plain http
    monkeypatch.setenv("LIVE_REFRESH", "off")
    monkeypatch.delenv("FANTASY_AUTH", raising=False)


def make_client(store_dir: Path) -> TestClient:
    return TestClient(
        api.create_app(data_dir=store_dir), base_url="http://localhost", headers=CSRF_HEADER
    )


def account_id_of(conn: sqlite3.Connection, email: str) -> int:
    return int(conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()[0])


def sign_in(store_dir: Path, email: str, *, admin: bool = False, grant: bool = False) -> TestClient:
    """A client signed in as `email`; `grant` gives that account the test league."""
    conn = accounts.connect(store_dir)
    if admin:
        accounts.create_admin(conn, email, GOOD)
    else:
        token = accounts.create_invite(conn, email, datetime.now(UTC))
        accounts.redeem_invite(conn, token, GOOD, datetime.now(UTC))
    if grant:
        conn.execute(
            "INSERT INTO account_leagues (account_id, league_id, added_at) VALUES (?, ?, ?)",
            (account_id_of(conn, email), LID, accounts.stamp(datetime.now(UTC))),
        )
        conn.commit()
    conn.close()
    client = make_client(store_dir)
    login = client.post("/api/auth/login", json={"email": email, "password": GOOD})
    assert login.status_code == 200, login.text
    return client
