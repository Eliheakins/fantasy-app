"""FantasyCalc market values, one fetch a day per distinct league setting.

The endpoint is undocumented with no stated terms or rate limit, so any failure is logged and
the stage still exits 0 with the previous table left in place.

Run: uv run python -m fantasy.stages.market_values
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from fantasy import store

log = logging.getLogger(__name__)
URL = "https://api.fantasycalc.com/values/current"
USER_AGENT = "fantasy-app personal tool (one fetch per league setting per day)"
TIMEOUT_SECONDS = 20
PPR_STEPS = (0.0, 0.5, 1.0)  # what the endpoint accepts


@dataclass(frozen=True)
class Setting:
    num_qbs: int
    num_teams: int
    ppr: float

    @property
    def key(self) -> str:
        return f"qb{self.num_qbs}_t{self.num_teams}_ppr{self.ppr:g}"


def setting_for(scoring_json: str, roster_positions: list[str], num_teams: int) -> Setting:
    rec = float(json.loads(scoring_json).get("rec", 0.0))
    ppr = min(PPR_STEPS, key=lambda step: abs(step - rec))
    return Setting(2 if "SUPER_FLEX" in roster_positions else 1, num_teams, ppr)


def fetch_values(setting: Setting) -> list[dict[str, Any]]:
    params: dict[str, str | int | float] = {
        "isDynasty": "false",
        "numQbs": setting.num_qbs,
        "numTeams": setting.num_teams,
        "ppr": setting.ppr,
    }
    resp = httpx.get(
        URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, list):
        raise RuntimeError(f"FantasyCalc returned {type(body).__name__}, not a list")
    return body


def to_frame(items: list[dict[str, Any]], fmt: str, fetched_at: str) -> pl.DataFrame:
    """Rows with a Sleeper id; draft picks and unmapped players are dropped."""
    rows = [
        {
            "format": fmt,
            "sleeper_id": str(i["player"]["sleeperId"]),
            "name": i["player"].get("name"),
            "position": i["player"].get("position"),
            "value": i["value"],
            "overall_rank": i.get("overallRank"),
            "position_rank": i.get("positionRank"),
            "trend_30_day": i.get("trend30Day"),
            "tier": i.get("maybeTier"),
            "fetched_at": fetched_at,
        }
        for i in items
        if i["player"].get("sleeperId") and i["player"].get("position") != "PICK"
    ]
    return pl.DataFrame(rows, schema=store.SCHEMAS["market_values"])


def run(
    data_dir: Path = store.DATA_DIR,
    fetch: Callable[[Setting], list[dict[str, Any]]] = fetch_values,
    now: str | None = None,
) -> int:
    """Rows fetched. A setting whose fetch fails keeps its previous rows."""
    now = now or datetime.now(UTC).isoformat(timespec="seconds")
    leagues = store.read_table("leagues", "raw", data_dir)
    settings = {
        setting_for(r["scoring_settings"], r["roster_positions"], r["num_teams"])
        for r in leagues.iter_rows(named=True)
    }
    try:
        kept = store.read_table("market_values", "raw", data_dir)
    except FileNotFoundError:
        kept = pl.DataFrame(schema=store.SCHEMAS["market_values"])
    fresh = [
        pl.col("format").eq(s.key) & pl.col("fetched_at").str.slice(0, 10).eq(now[:10])
        for s in settings
    ]
    done = set(kept.filter(pl.any_horizontal(*fresh))["format"]) if fresh else set()
    new: list[pl.DataFrame] = []
    for setting in sorted(settings, key=lambda s: s.key):
        if setting.key in done:
            continue
        try:
            new.append(to_frame(fetch(setting), setting.key, now))
        except Exception:
            log.exception(
                "market values fetch failed for %s; keeping the previous rows", setting.key
            )
    if not new:
        return 0
    replaced = {f["format"][0] for f in new if f.height}
    out = pl.concat([kept.filter(~pl.col("format").is_in(replaced)), *new])
    store.write_table("market_values", out, "raw", data_dir)
    return sum(f.height for f in new)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        print(f"{run()} market value rows fetched")
    except Exception:
        log.exception("market values stage failed; previous table left in place")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
