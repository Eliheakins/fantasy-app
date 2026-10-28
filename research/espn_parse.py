"""Turn the saved ESPN JSON (`espn_fetch.py`) into tables under `research/scratch/espn/`.

`lineups.parquet`: one row per season, regular-season week, team and rostered player, with the
lineup slot, whether the slot is a starting one, the points ESPN scored and the player's nflverse
gsis id (from the ff_playerids espn_id column; null where there is none, as for most D/ST).
`teams.parquet`: one row per season and team with the primary owner id, so a manager can be
followed across seasons. Third-party data: nothing here is committed.

    uv run python research/espn_parse.py
"""

import json
from pathlib import Path

import nflreadpy as nfl
import polars as pl

from fantasy import store

SCRATCH = store.ROOT / "research" / "scratch" / "espn"
SEASONS = (2023, 2024, 2025)
REGULAR_WEEKS = range(1, 15)  # matchupPeriodCount is 14
NOT_STARTING = (20, 21)  # bench and injured reserve
POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}


def lineups() -> pl.DataFrame:
    rows = []
    for season in SEASONS:
        for week in REGULAR_WEEKS:
            data = json.loads((SCRATCH / f"{season}_week{week:02d}.json").read_text())
            for game in data["schedule"]:
                if game["matchupPeriodId"] != week:
                    continue
                for side in ("home", "away"):
                    roster = game.get(side, {}).get("rosterForCurrentScoringPeriod")
                    if not roster:
                        continue
                    for entry in roster["entries"]:
                        pool = entry["playerPoolEntry"]
                        rows.append(
                            {
                                "season": season,
                                "week": week,
                                "team_id": game[side]["teamId"],
                                "espn_id": entry["playerId"],
                                "position": POSITIONS.get(pool["player"]["defaultPositionId"]),
                                "slot": entry["lineupSlotId"],
                                "starter": entry["lineupSlotId"] not in NOT_STARTING,
                                "points": float(pool["appliedStatTotal"]),
                            }
                        )
    ids = (
        nfl.load_ff_playerids()
        .filter(pl.col("espn_id").is_not_null() & pl.col("gsis_id").is_not_null())
        .select(pl.col("espn_id").cast(pl.Int64), "gsis_id")
        .unique("espn_id")
    )
    return pl.DataFrame(rows).join(ids, on="espn_id", how="left")


def teams() -> pl.DataFrame:
    rows = []
    for season in SEASONS:
        data = json.loads((SCRATCH / f"{season}_mTeam.json").read_text())
        rows += [
            {"season": season, "team_id": t["id"], "owner": t.get("primaryOwner"), "name": t["name"]}
            for t in data["teams"]
        ]
    return pl.DataFrame(rows)


def main() -> None:
    frame = lineups()
    frame.write_parquet(SCRATCH / "lineups.parquet")
    teams().write_parquet(SCRATCH / "teams.parquet")
    skill = frame.filter(pl.col("position").is_in(["QB", "RB", "WR", "TE"]))
    print(f"{frame.height} lineup rows; skill players with a gsis id: "
          f"{skill['gsis_id'].is_not_null().mean():.1%}")


if __name__ == "__main__":
    main()
