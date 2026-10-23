"""Archive one week's NFL player-prop lines from The Odds API (free tier, 500 credits a month).

Run: uv run python -m fantasy.stages.snapshot_odds [--dry-run]
Needs ODDS_API_KEY in the environment or in .env. Raw JSON only, nothing downstream reads it yet.
"""

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
CREDIT_FLOOR = 100  # stop before the monthly allowance runs out
PAUSE_SECONDS = 0.5
ODDS_DIR = store.DATA_DIR / "archive" / "odds"


def api_key(env_file: Path = store.ROOT / ".env") -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ODDS_API_KEY":
                key = value.strip()
    if not key:
        raise RuntimeError("ODDS_API_KEY is not set: export it or put it in .env")
    return key


def events_in_window(events: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    end = now + timedelta(days=WINDOW_DAYS)
    return [
        e
        for e in events
        if now <= datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) <= end
    ]


def snapshot_cost(n_events: int) -> int:
    return n_events * len(MARKETS)  # one credit per market per region per event


def log_credits(stamp: str, used: str | None, remaining: str | None, odds_dir: Path) -> None:
    odds_dir.mkdir(parents=True, exist_ok=True)
    log = odds_dir / "credit_log.csv"
    if not log.exists():
        log.write_text("snapshot,credits_used_total,credits_remaining\n")
    with log.open("a") as f:
        f.write(f"{stamp},{used},{remaining}\n")


def run(dry_run: bool = False, odds_dir: Path = ODDS_DIR, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    key = api_key()
    listing = httpx.get(f"{BASE}/events", params={"apiKey": key}, timeout=30)  # free call
    listing.raise_for_status()
    events = events_in_window(listing.json(), now)
    cost = snapshot_cost(len(events))
    remaining = listing.headers.get("x-requests-remaining")
    print(f"{len(events)} games in the next {WINDOW_DAYS} days, about {cost} credits")
    print(f"credits remaining before: {remaining}")
    if dry_run or not events:
        return
    if remaining is not None and int(float(remaining)) - cost < CREDIT_FLOOR:
        sys.exit(f"refusing: {remaining} credits left, floor is {CREDIT_FLOOR}")

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out = odds_dir / stamp
    out.mkdir(parents=True, exist_ok=True)
    used = left = None
    for e in events:
        resp = httpx.get(
            f"{BASE}/events/{e['id']}/odds",
            params={
                "apiKey": key,
                "regions": REGION,
                "markets": ",".join(MARKETS),
                "oddsFormat": "american",
            },
            timeout=30,
        )
        resp.raise_for_status()
        (out / f"{e['id']}.json").write_text(json.dumps(resp.json()))
        used, left = resp.headers.get("x-requests-used"), resp.headers.get("x-requests-remaining")
        time.sleep(PAUSE_SECONDS)
    log_credits(stamp, used, left, odds_dir)
    print(f"saved {len(events)} files to {out}; credits remaining: {left}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
