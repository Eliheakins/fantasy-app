import re

import pytest

from fantasy import api
from fantasy.auth import policy
from fantasy.auth.ratelimit import FailureLimiter

USER = {"id": 2, "email": "f@example.com", "is_admin": False}
ADMIN = {"id": 1, "email": "boss@example.com", "is_admin": True}


@pytest.mark.parametrize(
    ("method", "path", "account", "expected"),
    [
        ("GET", "/lineup", None, "allow"),  # the web app itself is public: it holds the login page
        ("GET", "/assets/app.js", None, "allow"),
        ("POST", "/api/auth/login", None, "allow"),
        ("POST", "/api/auth/redeem", None, "allow"),
        ("GET", "/api/leagues", None, "unauthorized"),
        ("GET", "/api/stat/manifest", None, "unauthorized"),
        ("POST", "/api/stat/nlq/intent", None, "unauthorized"),
        ("GET", "/api/leagues", USER, "allow"),
        ("GET", "/api/auth/me", USER, "allow"),
        ("POST", "/api/auth/logout", USER, "allow"),
        ("POST", "/api/auth/logout-everywhere", USER, "allow"),
        ("POST", "/api/leagues/colgate/trades/evaluate", USER, "allow"),
        ("POST", "/api/leagues/colgate/trades/find", USER, "allow"),
        ("POST", "/api/stat/nlq/intent", USER, "allow"),
        ("POST", "/api/me/sleeper/lookup", USER, "allow"),
        ("POST", "/api/me/leagues", USER, "allow"),
        ("DELETE", "/api/me/leagues/111", USER, "allow"),
        ("DELETE", "/api/me/leagues/111/extra", USER, "forbidden"),
        ("PUT", "/api/me/leagues/111/team", USER, "allow"),
        ("POST", "/api/live/refresh", USER, "forbidden"),
        ("POST", "/api/leagues/colgate/anything-new", USER, "forbidden"),
        ("DELETE", "/api/leagues/colgate", USER, "forbidden"),
        ("GET", "/api/admin/accounts", USER, "forbidden"),
        ("GET", "/api/admin/accounts", ADMIN, "allow"),
        ("POST", "/api/live/refresh", ADMIN, "allow"),
    ],
)
def test_the_decision_for_each_kind_of_request(
    method: str, path: str, account: dict | None, expected: str
) -> None:
    assert policy.decide(method, path, account) == expected


def test_every_write_the_app_has_is_one_we_decided_about(tmp_path) -> None:  # noqa: ANN001
    """A new write route must be added here on purpose: until then only the admin can use it."""
    paths = api.create_app(data_dir=tmp_path).openapi()["paths"]
    writes = sorted(
        f"{method.upper()} {path}"
        for path, ops in paths.items()
        for method in ops
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}
    )
    for write in writes:
        method, path = write.split(" ", 1)
        concrete = re.sub(r"\{[^}]+\}", "x", path)
        assert policy.decide(method, concrete, USER) in {"allow", "forbidden"}, write
    assert writes == [
        "DELETE /api/admin/accounts/{account_id}",
        "DELETE /api/me/leagues/{league_id}",
        "POST /api/admin/invites",
        "POST /api/admin/refresh",
        "POST /api/auth/login",
        "POST /api/auth/logout",
        "POST /api/auth/logout-everywhere",
        "POST /api/auth/redeem",
        "POST /api/leagues/{league}/trades/evaluate",
        "POST /api/leagues/{league}/trades/find",
        "POST /api/live/refresh",
        "POST /api/me/leagues",
        "POST /api/me/sleeper/lookup",
        "POST /api/stat/nlq/intent",
        "PUT /api/me/leagues/{league_id}/team",
    ]


def test_the_limiter_blocks_after_the_limit_and_frees_after_the_window() -> None:
    limiter = FailureLimiter(limit=3, window_s=60.0)
    for _ in range(3):
        assert not limiter.blocked("a", now=100.0)
        limiter.record("a", now=100.0)
    assert limiter.blocked("a", now=100.0)
    assert not limiter.blocked("b", now=100.0)  # another key is untouched
    assert not limiter.blocked("a", now=161.0)  # the window moved on


def test_a_success_clears_the_count() -> None:
    limiter = FailureLimiter(limit=2, window_s=60.0)
    limiter.record("a", now=0.0)
    limiter.record("a", now=1.0)
    assert limiter.blocked("a", now=2.0)
    limiter.clear("a")
    assert not limiter.blocked("a", now=2.0)
