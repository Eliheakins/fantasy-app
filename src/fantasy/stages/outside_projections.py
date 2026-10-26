"""Archive other sites' weekly stat projections for the current week, to test against later.

Only sites whose terms do not forbid scraping and storage (decisions log, 2026-10-25): FFToday.
FantasySharks' terms forbid robots ("Use any robot, spider ... to retrieve, index, 'data mine'"),
so it is left out. One request per position per run, a few seconds apart, top 50 per position
(FFToday's first page). Each position fails soft: a site change logs a warning and the rest of
`make refresh` runs on. Nothing downstream reads the archive yet; `map_to_gsis` joins it to
nflverse IDs for research.

Run: uv run python -m fantasy.stages.outside_projections
"""

import html
import json
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.stages.crosswalk import norm_team, normalize_name

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36"
)
PAUSE_SECONDS = 3.0
POSITIONS = ("QB", "RB", "WR", "TE")
FFTODAY_URL = "https://www.fftoday.com/rankings/playerwkproj.php"
FFTODAY_POS_ID = {"QB": 10, "RB": 20, "WR": 30, "TE": 40}
_SKILL = ("Att Yard TD Rec Yard TD", "rush_att rush_yd rush_td rec rec_yd rec_td")
# column labels between Opp and FPts, and the Sleeper stat keys they become
FFTODAY_LAYOUTS = {
    "QB": (
        "Comp Att Yard TD INT Att Yard TD",
        "pass_cmp pass_att pass_yd pass_td pass_int rush_att rush_yd rush_td",
    ),
    "RB": _SKILL,
    "WR": _SKILL,
    "TE": _SKILL,
}
_ROW = re.compile(r"<TR[^>]*>(.*?)</TR>", re.S | re.I)
_CELL = re.compile(r"<TD[^>]*>(.*?)</TD>", re.S | re.I)
_PLAYER = re.compile(r'href="/stats/players/(\d+)/', re.I)
_BOLD = re.compile(r"<B>(.*?)</B>", re.S | re.I)

Fetcher = Callable[[int, int, str], str]  # (season, week, position) -> page body


def _text(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()


def parse_fftoday(page: str, position: str) -> list[dict]:
    """Rows of FFToday's weekly projection page: source_id, name, team, stats (Sleeper keys).
    Raises ValueError when the column layout is not the one expected or no player row is found."""
    labels, keys = (s.split() for s in FFTODAY_LAYOUTS[position])
    first = _PLAYER.search(page)
    if first is None:
        raise ValueError(f"FFToday {position}: no player rows")
    head = [_text(b) for b in _BOLD.findall(page[page.rfind("Sort First", 0, first.start()) :])]
    head = head[: head.index("FPts") + 1] if "FPts" in head else head
    if head != ["Team", "Opp", *labels, "FPts"]:
        raise ValueError(f"FFToday {position}: unexpected column layout {head}")
    rows = []
    for row in _ROW.findall(page):
        player = _PLAYER.search(row)
        if player is None:
            continue
        cells = [_text(c) for c in _CELL.findall(row)]
        if len(cells) != len(keys) + 5:  # change, name, team, opponent, stats, points
            raise ValueError(f"FFToday {position}: row with {len(cells)} cells: {cells}")
        values = [float(v.replace(",", "")) for v in cells[4 : 4 + len(keys)]]
        rows.append(
            {
                "source_id": player.group(1),
                "name": cells[1],
                "team": norm_team(cells[2]),
                "stats": dict(zip(keys, values, strict=True)),
            }
        )
    return rows


def fetch_fftoday(season: int, week: int, position: str) -> str:
    params = {
        "Season": season,
        "GameWeek": week,
        "PosID": FFTODAY_POS_ID[position],
        "LeagueID": 1,
    }
    resp = httpx.get(FFTODAY_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


SOURCES: dict[str, tuple[Fetcher, Callable[[str, str], list[dict]]]] = {
    "fftoday": (fetch_fftoday, parse_fftoday),
}


def snapshot(
    source: str, fetch: Fetcher, season: int, week: int, fetched_at: str, pause: float
) -> pl.DataFrame:
    """One source's rows for every position; a position that fails is logged and skipped."""
    parse = SOURCES[source][1]
    rows = []
    for i, position in enumerate(POSITIONS):
        if i:
            time.sleep(pause)
        try:
            parsed = parse(fetch(season, week, position), position)
        except Exception as err:  # fail soft: a site change must not stop make refresh
            print(f"warning: {source} {position} week {week} skipped: {err!r}")
            continue
        rows += [
            {
                "source": source,
                "fetched_at": fetched_at,
                "season": season,
                "week": week,
                "position": position,
                **r,
                "stats": json.dumps(r["stats"], sort_keys=True),
            }
            for r in parsed
        ]
    return pl.DataFrame(rows, schema=store.SCHEMAS["outside_proj_snapshots"])


def run(
    data_dir: Path = store.DATA_DIR,
    sources: Sequence[str] | None = None,
    fetchers: dict[str, Fetcher] | None = None,
    pause: float = PAUSE_SECONDS,
) -> int:
    """Append the current week's projections from each source; returns the rows added."""
    config = load_config()
    names = config.outside_sources if sources is None else sources
    if not names:
        return 0
    fetch = {name: SOURCES[name][0] for name in names} | (fetchers or {})
    leagues = store.read_table("leagues", "raw", data_dir)
    week = int(leagues["current_week"].to_numpy().max())
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    new = pl.concat([snapshot(n, fetch[n], config.season, week, fetched_at, pause) for n in names])
    if new.is_empty():
        return 0
    archive = store.with_archive("outside_proj_snapshots", new, data_dir)
    store.write_table("outside_proj_snapshots", archive, "archive", data_dir)
    return new.height


def map_to_gsis(snaps: pl.DataFrame, people: pl.DataFrame) -> pl.DataFrame:
    """`snaps` with gsis_id: a unique match on name, position and team, else a unique match on
    name and position (a traded player), else null. `people`: gsis_id, name, position, team."""

    def keyed(df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            pl.col("name").map_elements(normalize_name, return_dtype=pl.String).alias("_name")
        )

    known = keyed(people).select("gsis_id", "_name", "position", "team").unique()

    def unique_on(cols: list[str], alias: str) -> pl.DataFrame:
        return (
            known.group_by(cols)
            .agg(pl.col("gsis_id").unique())
            .filter(pl.col("gsis_id").list.len() == 1)
            .select(*cols, pl.col("gsis_id").list.first().alias(alias))
        )

    return (
        keyed(snaps)
        .join(
            unique_on(["_name", "position", "team"], "_by_team"),
            on=["_name", "position", "team"],
            how="left",
        )
        .join(unique_on(["_name", "position"], "_by_name"), on=["_name", "position"], how="left")
        .with_columns(pl.coalesce("_by_team", "_by_name").alias("gsis_id"))
        .drop("_name", "_by_team", "_by_name")
    )


def people(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Names, positions and teams known for each gsis_id: nflverse weekly stats and injury
    reports (every team a player had) and Sleeper's players file (his team now)."""
    stats = store.read_table("nfl_player_stats", "raw", data_dir).select(
        pl.col("player_id").alias("gsis_id"),
        pl.col("player_display_name").alias("name"),
        "position",
        "team",
    )
    injuries = store.read_table("nfl_injuries", "raw", data_dir).select(
        "gsis_id", pl.col("full_name").alias("name"), "position", "team"
    )
    ids = store.read_table("id_map", "derived", data_dir).select("sleeper_id", "gsis_id")
    sleeper = (
        store.read_table("sleeper_players", "raw", data_dir)
        .drop("gsis_id")
        .join(ids, on="sleeper_id")
        .select("gsis_id", pl.col("full_name").alias("name"), "position", "team")
        .with_columns(pl.col("team").map_elements(norm_team, return_dtype=pl.String))
    )
    return pl.concat([stats, injuries, sleeper]).drop_nulls().unique()


if __name__ == "__main__":
    print(f"{run()} rows added to the archive")
