"""Auth fails closed: bad mode, public-but-open warning, middleware order, atomic login throttle."""

import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fantasy import api
from fantasy.auth import accounts, passwords, routes
from fantasy.auth.ratelimit import FailureLimiter

CSRF = {"X-Requested-With": "fantasy-app"}
GOOD = "a long enough password"


@pytest.fixture(autouse=True)
def quick_and_isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(passwords, "COST_N", 2**10)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("LIVE_REFRESH", "off")
    monkeypatch.delenv("FANTASY_AUTH", raising=False)
    monkeypatch.delenv(routes.HOSTS_ENV, raising=False)
    monkeypatch.setattr(routes, "limiter", FailureLimiter(limit=5, window_s=60.0))
    routes._warn_open_public_gate.cache_clear()
    yield
    routes._warn_open_public_gate.cache_clear()


def _app_client(store_dir: Path) -> TestClient:
    return TestClient(api.create_app(data_dir=store_dir), base_url="http://localhost", headers=CSRF)


def _secured(store_dir: Path) -> None:
    conn = accounts.connect(store_dir)
    accounts.create_admin(conn, "boss@example.com", GOOD)
    conn.close()


# --- mode ------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["requierd", "true", "0", "OFFF"])
def test_an_unknown_auth_mode_stops_the_app_at_startup(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("FANTASY_AUTH", value)
    with pytest.raises(ValueError, match="FANTASY_AUTH"):
        api.create_app(data_dir=store_dir)


@pytest.mark.parametrize("value", ["on", "off", "required", " Required ", ""])
def test_the_known_modes_start_and_the_effective_one_is_logged(
    store_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    value: str,
) -> None:
    monkeypatch.setenv("FANTASY_AUTH", value)
    with caplog.at_level(logging.INFO, logger=routes.log.name):
        api.create_app(data_dir=store_dir)
    expected = value.strip().lower() or "on"
    assert f"Login gate mode: {expected}" in caplog.text


def test_a_public_server_with_no_accounts_warns_once_that_login_is_open(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(routes.HOSTS_ENV, "fantasy.example.com")
    with caplog.at_level(logging.WARNING, logger=routes.log.name), _app_client(store_dir) as c:
        assert c.get("/api/leagues").status_code == 200  # no auth.db: open, as designed
        assert c.get("/api/leagues").status_code == 200
    assert [r.levelno for r in caplog.records].count(logging.WARNING) == 1
    assert "NOT enforced" in caplog.text


def test_an_empty_accounts_table_warns_too(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    accounts.connect(store_dir).close()  # auth.db exists, no account in it
    monkeypatch.setenv(routes.HOSTS_ENV, "fantasy.example.com")
    with caplog.at_level(logging.WARNING, logger=routes.log.name), _app_client(store_dir) as c:
        assert c.get("/api/leagues").status_code == 200
    assert "NOT enforced" in caplog.text


def test_a_local_run_does_not_warn(store_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=routes.log.name), _app_client(store_dir) as c:
        assert c.get("/api/leagues").status_code == 200
    assert "NOT enforced" not in caplog.text


def test_required_mode_and_a_real_account_do_not_warn(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(routes.HOSTS_ENV, "fantasy.example.com")
    monkeypatch.setenv("FANTASY_AUTH", "required")
    with caplog.at_level(logging.WARNING, logger=routes.log.name), _app_client(store_dir) as c:
        assert c.get("/api/leagues").status_code == 401
    _secured(store_dir)
    monkeypatch.delenv("FANTASY_AUTH")
    with caplog.at_level(logging.WARNING, logger=routes.log.name), _app_client(store_dir) as c:
        assert c.get("/api/leagues").status_code == 401
    assert "NOT enforced" not in caplog.text


# --- middleware ------------------------------------------------------------------------


@pytest.fixture
def no_database(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    touched: list[str] = []

    def spy(*args: Any, **kwargs: Any) -> Any:
        touched.append("open_db")
        raise AssertionError("the auth database was opened")

    monkeypatch.setattr(accounts, "open_db", spy)
    return touched


def test_static_paths_never_touch_the_auth_database(
    store_dir: Path, no_database: list[str]
) -> None:
    with _app_client(store_dir) as c:
        for path in ("/", "/assets/app.js", "/lineup", "/api"):
            c.get(path)
    assert no_database == []


def test_a_request_for_an_api_path_still_resolves_the_account(
    store_dir: Path, no_database: list[str]
) -> None:
    _secured(store_dir)
    with _app_client(store_dir) as c, pytest.raises(AssertionError, match="auth database"):
        c.get("/api/leagues")
    assert no_database == ["open_db"]


def test_an_unknown_host_is_refused_before_the_login_gate(
    store_dir: Path, no_database: list[str]
) -> None:
    _secured(store_dir)
    with _app_client(store_dir) as c:
        response = c.get("/api/leagues", headers={"Host": "evil.example.com"})
    assert response.status_code == 400
    assert no_database == []


def test_a_write_without_the_csrf_header_is_refused_before_the_login_gate(
    store_dir: Path, no_database: list[str]
) -> None:
    _secured(store_dir)
    with TestClient(api.create_app(data_dir=store_dir), base_url="http://localhost") as c:
        response = c.post("/api/auth/login", json={"email": "a@b.co", "password": GOOD})
    assert response.status_code == 403
    assert no_database == []


# --- login throttle --------------------------------------------------------------------


def test_attempt_counts_before_the_check_so_a_burst_cannot_get_past_the_limit() -> None:
    limiter = FailureLimiter(limit=5, window_s=60.0)
    allowed: list[bool] = []
    start = threading.Barrier(40)

    def guess() -> None:
        start.wait()
        allowed.append(limiter.attempt(("ip:1", "email:a"), 100.0))

    threads = [threading.Thread(target=guess) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 5


def test_a_full_key_blocks_the_attempt_and_charges_nothing_else() -> None:
    limiter = FailureLimiter(limit=2, window_s=60.0)
    assert limiter.attempt(("ip:1",), 0.0) and limiter.attempt(("ip:1",), 1.0)
    assert not limiter.attempt(("ip:1", "email:a"), 2.0)
    assert not limiter.blocked("email:a", 2.0)  # the refused attempt left no count behind
    assert limiter.attempt(("ip:1",), 61.0)  # the window slides


def test_refund_takes_back_one_count() -> None:
    limiter = FailureLimiter(limit=2, window_s=60.0)
    limiter.attempt(("k",), 0.0)
    limiter.attempt(("k",), 1.0)
    limiter.refund("k")
    assert not limiter.blocked("k", 2.0)
    limiter.refund("k")
    limiter.refund("k")  # nothing left: no error
    assert limiter._failures == {}


def test_expired_keys_of_attackers_who_never_return_are_pruned() -> None:
    limiter = FailureLimiter(limit=5, window_s=60.0)
    for i in range(100):
        limiter.attempt((f"ip:{i}",), 0.0)
    limiter.attempt(("ip:new",), 120.0)
    assert list(limiter._failures) == ["ip:new"]


def test_the_sixth_login_in_a_minute_is_refused_and_a_success_does_not_use_up_the_address(
    store_dir: Path,
) -> None:
    _secured(store_dir)
    with _app_client(store_dir) as c:
        for _ in range(4):
            ok = c.post("/api/auth/login", json={"email": "boss@example.com", "password": GOOD})
            assert ok.status_code == 200
        for _ in range(5):
            bad = c.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"})
            assert bad.status_code == 401
        blocked = c.post("/api/auth/login", json={"email": "y@example.com", "password": "nope"})
    assert blocked.status_code == 429
