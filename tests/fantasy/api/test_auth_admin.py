from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fantasy import _runs, api, refresh_queue
from fantasy.auth import accounts, passwords

CSRF = {"X-Requested-With": "fantasy-app"}
GOOD = "a long enough password"
ADMIN = "boss@example.com"
FRIEND = "friend@example.com"


@pytest.fixture(autouse=True)
def quick_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "COST_N", 2**10)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("LIVE_REFRESH", "off")
    monkeypatch.delenv("FANTASY_AUTH", raising=False)


def client_for(store_dir: Path) -> TestClient:
    return TestClient(api.create_app(data_dir=store_dir), base_url="http://localhost", headers=CSRF)


def sign_in(store_dir: Path, email: str, *, admin: bool = False) -> TestClient:
    conn = accounts.connect(store_dir)
    if admin:
        accounts.create_admin(conn, email, GOOD)
    else:
        token = accounts.create_invite(conn, email, datetime.now(UTC))
        accounts.redeem_invite(conn, token, GOOD, datetime.now(UTC))
    conn.close()
    client = client_for(store_dir)
    assert (
        client.post("/api/auth/login", json={"email": email, "password": GOOD}).status_code == 200
    )
    return client


@pytest.fixture
def admin(store_dir: Path) -> TestClient:
    return sign_in(store_dir, ADMIN, admin=True)


def test_the_admin_sees_every_account_without_any_hash(admin: TestClient, store_dir: Path) -> None:
    conn = accounts.connect(store_dir)
    accounts.create_invite(conn, FRIEND, datetime.now(UTC))
    conn.close()
    listed = admin.get("/api/admin/accounts").json()["data"]
    assert [
        (a["email"], a["is_admin"], a["has_password"], a["invite_pending"]) for a in listed
    ] == [
        (ADMIN, True, True, False),
        (FRIEND, False, False, True),
    ]
    assert "password" not in str(listed).lower().replace("has_password", "")


def test_a_friend_cannot_use_any_admin_route(store_dir: Path) -> None:
    friend = sign_in(store_dir, FRIEND)
    assert friend.get("/api/admin/accounts").status_code == 403
    assert friend.post("/api/admin/invites", json={"email": "x@example.com"}).status_code == 403
    assert friend.delete("/api/admin/accounts/1").status_code == 403
    assert friend.get("/api/admin/refresh").status_code == 403
    assert friend.post("/api/admin/refresh").status_code == 403


def test_a_new_invite_returns_a_link_that_lets_that_person_in(
    admin: TestClient, store_dir: Path
) -> None:
    created = admin.post("/api/admin/invites", json={"email": " New@Example.com "})
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["email"] == "new@example.com"
    assert data["path"].startswith("/invite/")
    assert data["valid_days"] == accounts.INVITE_DAYS

    token = data["path"].removeprefix("/invite/")
    friend = client_for(store_dir)
    redeemed = friend.post("/api/auth/redeem", json={"token": token, "password": GOOD})
    assert redeemed.status_code == 200
    assert friend.get("/api/auth/me").json()["data"]["email"] == "new@example.com"


def test_a_second_link_for_the_same_email_replaces_the_first_and_resets_the_password(
    admin: TestClient, store_dir: Path
) -> None:
    friend = sign_in(store_dir, FRIEND)
    link = admin.post("/api/admin/invites", json={"email": FRIEND}).json()["data"]["path"]
    token = link.removeprefix("/invite/")
    other = client_for(store_dir)
    assert (
        other.post(
            "/api/auth/redeem", json={"token": token, "password": "a brand new password"}
        ).status_code
        == 200
    )
    assert (
        client_for(store_dir)
        .post("/api/auth/login", json={"email": FRIEND, "password": GOOD})
        .status_code
        == 401
    )
    assert friend.get("/api/auth/me").status_code == 401  # the old session ended with the reset


def test_a_malformed_email_is_refused(admin: TestClient) -> None:
    refused = admin.post("/api/admin/invites", json={"email": "not an email"})
    assert refused.status_code in {400, 422}


def test_removing_an_account_signs_the_person_out_and_ends_their_login(
    admin: TestClient, store_dir: Path
) -> None:
    friend = sign_in(store_dir, FRIEND)
    friend_id = next(
        a["id"] for a in admin.get("/api/admin/accounts").json()["data"] if a["email"] == FRIEND
    )
    assert admin.delete(f"/api/admin/accounts/{friend_id}").status_code == 200
    assert friend.get("/api/auth/me").status_code == 401
    assert (
        client_for(store_dir)
        .post("/api/auth/login", json={"email": FRIEND, "password": GOOD})
        .status_code
        == 401
    )
    assert [a["email"] for a in admin.get("/api/admin/accounts").json()["data"]] == [ADMIN]


def test_the_admin_account_cannot_be_removed(admin: TestClient) -> None:
    [me] = admin.get("/api/admin/accounts").json()["data"]
    refused = admin.delete(f"/api/admin/accounts/{me['id']}")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "invalid"
    assert admin.get("/api/auth/me").status_code == 200


def test_removing_an_account_that_is_not_there_is_a_404(admin: TestClient) -> None:
    assert admin.delete("/api/admin/accounts/9999").status_code == 404


def test_refresh_admin_shows_the_state_and_recent_runs(admin: TestClient, store_dir: Path) -> None:
    now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    _runs.record_run("sync_sleeper", "ok", None, store_dir, now=now, run_id="r1", duration_s=2.0)
    _runs.record_run("project", "failed", "boom", store_dir, now=now, run_id="r1", duration_s=3.0)
    _runs.record_run("sync_sleeper", "ok", None, store_dir, now=now, run_id="r2", duration_s=2.5)
    data = admin.get("/api/admin/refresh").json()["data"]
    assert data["state"] == "idle"
    runs = {r["run_id"]: r for r in data["runs"]}
    assert (runs["r1"]["stages"], runs["r1"]["failed"], runs["r1"]["seconds"]) == (2, 1, 5.0)
    assert (runs["r2"]["stages"], runs["r2"]["failed"]) == (1, 0)


def test_refresh_now_queues_a_refresh(admin: TestClient, store_dir: Path) -> None:
    assert admin.post("/api/admin/refresh").status_code == 200
    assert refresh_queue.status(store_dir)["state"] == "queued"
    assert admin.get("/api/admin/refresh").json()["data"]["state"] == "queued"
