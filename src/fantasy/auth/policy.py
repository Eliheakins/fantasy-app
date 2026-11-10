"""Who may do what: one pure function, so the whole rule fits on a page and can be tested.

Everything under /api needs a signed-in account except logging in and redeeming an invite. The
web app's own files are public, because they hold the login page. A signed-in friend may read
anything and use the three routes that only compute (trade evaluation and search, Ask); every
other write is the admin's, so a new write route is closed to friends until it is listed here.
"""

import re
from typing import Any, Literal

Decision = Literal["allow", "unauthorized", "forbidden"]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PUBLIC = frozenset({("POST", "/api/auth/login"), ("POST", "/api/auth/redeem")})
FRIEND_WRITES = (
    re.compile(r"^/api/auth/logout$"),
    re.compile(r"^/api/leagues/[^/]+/trades/(evaluate|find)$"),
    re.compile(r"^/api/stat/nlq/intent$"),
    re.compile(r"^/api/me/sleeper/lookup$"),  # add and remove your own leagues
    re.compile(r"^/api/me/leagues(/[^/]+)?$"),
    re.compile(r"^/api/me/leagues/[^/]+/team$"),  # pick which team in it is yours
)
ADMIN_PREFIX = "/api/admin/"


def decide(method: str, path: str, account: dict[str, Any] | None) -> Decision:
    if not path.startswith("/api/"):
        return "allow"
    if (method, path) in PUBLIC:
        return "allow"
    if account is None:
        return "unauthorized"
    if account["is_admin"]:
        return "allow"
    if path.startswith(ADMIN_PREFIX):
        return "forbidden"
    if method in SAFE_METHODS:
        return "allow"
    return "allow" if any(rule.match(path) for rule in FRIEND_WRITES) else "forbidden"
