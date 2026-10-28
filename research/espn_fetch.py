"""Save raw ESPN fantasy JSON for the YinzBurgh league's earlier seasons, for a parser to read.

The league ran on ESPN in 2023 to 2025 (earlier years answer 404 under this id) and is private, so
it needs the browser cookies `espn_s2` and `SWID`: put ESPN_S2 and ESPN_SWID (with its braces) in
the gitignored `.env`, never in a command or a chat. Output goes to `research/scratch/espn/`,
which is gitignored: it is third-party data and is never committed. Reads only, about 110 requests.

    uv run python research/espn_fetch.py
"""

import json
import os
import time
from pathlib import Path

import httpx

from fantasy import store
from fantasy.stages.snapshot_odds import parse_env_line

LEAGUE_ID = 1470881390
SEASONS = (2023, 2024, 2025)
WEEKS = range(1, 19)
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league}"
SEASON_VIEWS = ("mSettings", "mTeam", "mRoster")
WEEK_VIEWS = ("mMatchup", "mMatchupScore", "mBoxscore")
PAUSE_SECONDS = 0.5
OUT = store.ROOT / "research" / "scratch" / "espn"


def cookies(env_file: Path = store.ROOT / ".env") -> dict[str, str]:
    found = {k: os.environ[k] for k in ("ESPN_S2", "ESPN_SWID") if k in os.environ}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            parsed = parse_env_line(line)
            if parsed and parsed[0] in ("ESPN_S2", "ESPN_SWID"):
                found.setdefault(*parsed)
    if len(found) < 2:
        raise RuntimeError("ESPN_S2 and ESPN_SWID are not set: put both in .env")
    return {"espn_s2": found["ESPN_S2"], "SWID": found["ESPN_SWID"]}


def fetch(client: httpx.Client, season: int, name: str, params: list[tuple[str, str | int]]) -> None:
    path = OUT / f"{season}_{name}.json"
    if path.exists():
        return
    response = client.get(BASE.format(season=season, league=LEAGUE_ID), params=params)
    if response.status_code != 200:
        print(f"{season} {name}: HTTP {response.status_code} {response.text[:120]}")
        return
    path.write_text(json.dumps(response.json()))
    time.sleep(PAUSE_SECONDS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "fantasy-app personal tool"}
    with httpx.Client(cookies=cookies(), headers=headers, timeout=30) as client:
        for season in SEASONS:
            for view in SEASON_VIEWS:
                fetch(client, season, view, [("view", view)])
            for week in WEEKS:
                params: list[tuple[str, str | int]] = [("view", v) for v in WEEK_VIEWS]
                fetch(client, season, f"week{week:02d}", [*params, ("scoringPeriodId", week)])
                # transactions only come back for one scoring period at a time
                tx = [("view", "mTransactions2"), ("scoringPeriodId", week)]
                fetch(client, season, f"tx{week:02d}", tx)
    print(f"saved under {OUT}")


if __name__ == "__main__":
    main()
