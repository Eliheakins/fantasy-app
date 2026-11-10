from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fantasy import api
from fantasy.auth import accounts, passwords, routes

CSRF = {"X-Requested-With": "fantasy-app"}
GOOD = "a long enough password"
ADMIN = "boss@example.com"


@pytest.fixture(autouse=True)
def quick_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "COST_N", 2**10)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")  # the test client speaks plain http
    monkeypatch.setenv("LIVE_REFRESH", "off")
    monkeypatch.delenv("FANTASY_AUTH", raising=False)
    monkeypatch.setattr(routes, "limiter", routes.FailureLimiter(limit=5, window_s=60.0))


def make_client(store_dir: Path) -> TestClient:
    return TestClient(api.create_app(data_dir=store_dir), base_url="http://localhost", headers=CSRF)


@pytest.fixture
def secured(store_dir: Path) -> Iterator[TestClient]:
    conn = accounts.connect(store_dir)
    accounts.create_admin(conn, ADMIN, GOOD)
    conn.close()
    with make_client(store_dir) as client:
        yield client


def login(client: TestClient, email: str = ADMIN, password: str = GOOD) -> Any:
    return client.post("/api/auth/login", json={"email": email, "password": password})


def invite(store_dir: Path, email: str) -> str:
    conn = accounts.connect(store_dir)
    token = accounts.create_invite(conn, email, datetime.now(UTC))
    conn.close()
    return token


def test_without_an_account_in_the_data_folder_the_app_stays_open(client: TestClient) -> None:
    assert client.get("/api/leagues").status_code == 200  # today's local behaviour


def test_the_auth_switch_can_turn_the_gate_off(
    secured: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FANTASY_AUTH", "off")
    assert secured.get("/api/leagues").status_code == 200


def test_once_an_admin_exists_signed_out_requests_are_refused(secured: TestClient) -> None:
    for path in ("/api/leagues", "/api/status", "/api/stat/manifest", "/api/auth/me"):
        response = secured.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthorized"
    intent = secured.post("/api/stat/nlq/intent", json={"question": "x"})
    assert intent.status_code == 401


def test_login_sets_a_safe_cookie_and_opens_the_api(
    secured: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AUTH_COOKIE_SECURE")  # production setting: Secure by default
    response = login(secured)
    assert response.status_code == 200
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    secured.cookies.clear()
    login(secured)  # the plain-http test client can only keep a non-Secure cookie
    assert secured.get("/api/leagues").status_code == 200
    me = secured.get("/api/auth/me").json()["data"]
    assert me == {"email": ADMIN, "is_admin": True, "sleeper_user_id": None}


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(secured: TestClient) -> None:
    wrong = login(secured, password="not the password at all")
    unknown = login(secured, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == unknown.json()["error"]


def test_after_logout_the_session_no_longer_works(secured: TestClient) -> None:
    login(secured)
    assert secured.post("/api/auth/logout").status_code == 200
    assert secured.get("/api/leagues").status_code == 401


def test_the_sixth_wrong_attempt_in_a_minute_is_refused_even_with_the_right_password(
    secured: TestClient,
) -> None:
    for _ in range(5):
        assert login(secured, password="wrong wrong wrong").status_code == 401
    blocked = login(secured)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "busy"


def test_an_invited_friend_sets_a_password_once_and_is_signed_in(
    secured: TestClient, store_dir: Path
) -> None:
    token = invite(store_dir, "friend@example.com")
    friend = make_client(store_dir)
    redeemed = friend.post("/api/auth/redeem", json={"token": token, "password": GOOD})
    assert redeemed.status_code == 200
    assert friend.get("/api/auth/me").json()["data"]["email"] == "friend@example.com"
    again = make_client(store_dir).post(
        "/api/auth/redeem", json={"token": token, "password": "another long password"}
    )
    assert again.status_code == 400
    assert "already used" in again.json()["error"]["message"]


def test_a_short_password_is_explained_not_accepted(secured: TestClient, store_dir: Path) -> None:
    token = invite(store_dir, "friend@example.com")
    response = make_client(store_dir).post(
        "/api/auth/redeem", json={"token": token, "password": "short"}
    )
    assert response.status_code == 400
    assert "at least" in response.json()["error"]["message"]


def test_a_friend_can_read_and_compute_but_cannot_write_or_see_admin_routes(
    secured: TestClient, store_dir: Path
) -> None:
    friend = make_client(store_dir)
    token = invite(store_dir, "friend@example.com")
    friend.post("/api/auth/redeem", json={"token": token, "password": GOOD})
    assert friend.get("/api/leagues").status_code == 200
    assert friend.post("/api/live/refresh").status_code == 403
    assert friend.get("/api/admin/accounts").status_code == 403
    login(secured)
    assert secured.post("/api/live/refresh").status_code not in {401, 403}  # the admin may


def test_the_client_address_comes_from_the_proxy_only_when_the_peer_is_local() -> None:
    class Peer:
        def __init__(self, host: str, forwarded: str | None) -> None:
            self.client = type("C", (), {"host": host})()
            self.headers = {"x-forwarded-for": forwarded} if forwarded else {}

    assert routes.client_ip(Peer("127.0.0.1", "203.0.113.9, 198.51.100.4")) == "198.51.100.4"
    assert routes.client_ip(Peer("203.0.113.9", "198.51.100.4")) == "203.0.113.9"  # not trusted
    assert routes.client_ip(Peer("127.0.0.1", None)) == "127.0.0.1"


def test_required_mode_locks_a_server_that_has_no_account_yet(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a public server the gate must not wait for the first account: until the admin exists,
    nothing is served and nobody can sign in, instead of everything being open."""
    monkeypatch.setenv("FANTASY_AUTH", "required")
    for path in ("/api/leagues", "/api/status", "/api/auth/me"):
        assert client.get(path).status_code == 401, path
    assert login(client).status_code == 401


def test_required_mode_serves_normally_once_signed_in(
    secured: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FANTASY_AUTH", "required")
    assert login(secured).status_code == 200
    assert secured.get("/api/leagues").status_code == 200
