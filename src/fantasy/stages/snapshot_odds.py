"""Archive one week's NFL player-prop lines from The Odds API (free tier, 500 credits a month).

Run: uv run python -m fantasy.stages.snapshot_odds [--dry-run] [--slate]
--slate pulls only the coming slate, near kickoff: Thursday evening for that night's game, Sunday
about 11:45 ET for Sunday and Monday (about 84 credits a week instead of one 7-day pull).
Needs ODDS_API_KEY in the environment or in .env. Raw JSON; prop_points turns it into points.
"""

import calendar
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from fantasy import store

BASE = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"
MARKETS = (
    "player_pass_yds",
    "player_pass_tds",
    "player_rush_yds",
    "player_receptions",
    "player_reception_yds",
    "player_anytime_td",
)
REGION = "us"
WINDOW_DAYS = 7  # one week of games per snapshot
EASTERN = ZoneInfo("America/New_York")
SLATE_END_HOUR = 6
SLATE_END_DAYS = (calendar.TUESDAY, calendar.FRIDAY)
CREDIT_FLOOR = 100  # stop before the monthly allowance runs out
PAUSE_SECONDS = 0.5
EVENT_ID = re.compile(r"[A-Za-z0-9]+", re.ASCII)  # becomes a file name
ODDS_DIR = store.DATA_DIR / "archive" / "odds"


def parse_env_line(line: str) -> tuple[str, str] | None:
    """One `.env` line as (name, value): comments and blanks are skipped, an `export ` prefix and
    one pair of surrounding quotes are dropped."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    line = line.removeprefix("export ").lstrip()
    name, sep, value = line.partition("=")
    if not sep:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return name.strip(), value


def api_key(env_file: Path = store.ROOT / ".env") -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            parsed = parse_env_line(line)
            if parsed and parsed[0] == "ODDS_API_KEY":
                key = parsed[1]
    if not key:
        raise RuntimeError("ODDS_API_KEY is not set: export it or put it in .env")
    return key


def _get(url: str, params: dict[str, str]) -> httpx.Response:
    """GET that raises without the request URL, which carries the API key."""
    resp = httpx.get(url, params=params, timeout=30)
    if resp.is_error:
        raise RuntimeError(f"Odds API returned {resp.status_code} for {url.removeprefix(BASE)}")
    return resp


def slate_end(now: datetime) -> datetime:
    """The next 06:00 Eastern on a Friday or Tuesday: a Thursday-evening pull covers that night's
    game, a Sunday-morning pull covers Sunday and Monday."""
    local = now.astimezone(EASTERN)
    end = local.replace(hour=SLATE_END_HOUR, minute=0, second=0, microsecond=0)
    while end <= local or end.weekday() not in SLATE_END_DAYS:
        end += timedelta(days=1)  # wall-clock arithmetic in EASTERN, so 06:00 holds across DST
    return end.astimezone(UTC)


def events_in_window(
    events: list[dict[str, Any]], now: datetime, end: datetime | None = None
) -> list[dict[str, Any]]:
    end = end or now + timedelta(days=WINDOW_DAYS)
    return [e for e in events if now <= datetime.fromisoformat(e["commence_time"]) <= end]


def snapshot_cost(n_events: int) -> int:
    return n_events * len(MARKETS)  # one credit per market per region per event


def log_credits(stamp: str, used: str | None, remaining: str | None, odds_dir: Path) -> None:
    odds_dir.mkdir(parents=True, exist_ok=True)
    log = odds_dir / "credit_log.csv"
    if not log.exists():
        log.write_text("snapshot,credits_used_total,credits_remaining\n")
    with log.open("a") as f:
        f.write(f"{stamp},{used},{remaining}\n")


def run(
    dry_run: bool = False,
    odds_dir: Path = ODDS_DIR,
    now: datetime | None = None,
    slate: bool = False,
) -> None:
    """`slate`: only games up to `slate_end` (one pull near kickoff per slate) instead of 7 days."""
    now = now or datetime.now(UTC)
    key = api_key()
    listing = _get(f"{BASE}/events", {"apiKey": key})  # free call
    end = slate_end(now) if slate else now + timedelta(days=WINDOW_DAYS)
    events = events_in_window(listing.json(), now, end)
    if not all(EVENT_ID.fullmatch(str(e["id"])) for e in events):
        raise RuntimeError("Odds API returned an event id that is not alphanumeric")
    cost = snapshot_cost(len(events))
    remaining = listing.headers.get("x-requests-remaining")
    print(f"{len(events)} games until {end:%Y-%m-%d %H:%M} UTC, about {cost} credits")
    print(f"credits remaining before: {remaining}")
    if dry_run or not events:
        return
    if remaining is not None and int(float(remaining)) - cost < CREDIT_FLOOR:
        sys.exit(f"refusing: {remaining} credits left, floor is {CREDIT_FLOOR}")

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    partial = odds_dir / f"{stamp}.partial"  # only a finished snapshot gets the plain name
    partial.mkdir(parents=True, exist_ok=True)
    used = left = None
    try:
        for e in events:
            resp = _get(
                f"{BASE}/events/{e['id']}/odds",
                {
                    "apiKey": key,
                    "regions": REGION,
                    "markets": ",".join(MARKETS),
                    "oddsFormat": "american",
                },
            )
            (partial / f"{e['id']}.json").write_text(json.dumps(resp.json()))
            used = resp.headers.get("x-requests-used")
            left = resp.headers.get("x-requests-remaining")
            time.sleep(PAUSE_SECONDS)
    finally:
        if used is not None:  # credits were spent even if a later call failed
            log_credits(stamp, used, left, odds_dir)
    out = odds_dir / stamp
    partial.rename(out)
    print(f"saved {len(events)} files to {out}; credits remaining: {left}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv, slate="--slate" in sys.argv)
