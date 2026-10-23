"""Map Sleeper player IDs to nflverse (gsis) IDs.

Order of trust: manual override, nflverse ff_playerids Sleeper ID, the gsis ID in Sleeper's own
players file, then a unique name + position + team match. Defenses map by team code. Players
with no match stay in the table with match_method "none", so the dashboard can list them.
Players on your own rosters that fail to map stop the run.

Run: uv run python -m fantasy.stages.crosswalk
"""

import re
from collections import defaultdict

import nflreadpy as nfl
import polars as pl

from fantasy import store
from fantasy.config import ROOT

OVERRIDES = ROOT / "overrides" / "id_map.csv"
# Sleeper and nflverse's ID table use older or different team codes than nflverse's own stats.
TEAM_MAP = {
    "LAR": "LA",
    "GBP": "GB",
    "KCC": "KC",
    "LVR": "LV",
    "NEP": "NE",
    "NOS": "NO",
    "SFO": "SF",
    "TBB": "TB",
    "JAC": "JAX",
    "WSH": "WAS",
}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_team(team: str | None) -> str | None:
    return TEAM_MAP.get(team, team) if team else None


def norm_position(position: str | None) -> str | None:
    return "K" if position == "PK" else position


def normalize_name(name: str) -> str:
    letters = re.sub(r"[^a-z ]", "", name.lower())
    return " ".join(t for t in letters.split() if t not in SUFFIXES)


def build_id_map(
    players: pl.DataFrame, ffids: pl.DataFrame, overrides: pl.DataFrame
) -> pl.DataFrame:
    by_sleeper: dict[str, str] = {}
    by_name: dict[tuple[str, str | None, str | None], set[str]] = defaultdict(set)
    for r in ffids.iter_rows(named=True):
        known_id = r["gsis_id"]
        if not known_id:
            continue
        if r["sleeper_id"] is not None:
            by_sleeper[str(r["sleeper_id"])] = known_id
        name = normalize_name(r["merge_name"] or r["name"] or "")
        by_name[(name, norm_position(r["position"]), norm_team(r["team"]))].add(known_id)
    manual = {r["sleeper_id"]: r["gsis_id"] for r in overrides.iter_rows(named=True)}

    rows = []
    for p in players.iter_rows(named=True):
        sid, pos = p["sleeper_id"], p["position"]
        team = norm_team(p["team"])
        gsis: str | None = None
        if pos == "DEF":
            method, team = "team_defense", norm_team(sid)
        elif sid in manual:
            gsis, method = manual[sid], "override"
        elif sid in by_sleeper:
            gsis, method = by_sleeper[sid], "ffplayerids"
        elif p["gsis_id"]:
            gsis, method = p["gsis_id"], "sleeper_file"
        else:
            ids = by_name.get((normalize_name(p["full_name"]), pos, team), set())
            gsis, method = (next(iter(ids)), "name_pos_team") if len(ids) == 1 else (None, "none")
        rows.append({"sleeper_id": sid, "gsis_id": gsis, "nfl_team": team, "match_method": method})
    return pl.DataFrame(rows, schema=store.SCHEMAS["id_map"])


def unmapped_on_my_rosters(
    id_map: pl.DataFrame, rosters: pl.DataFrame, teams: pl.DataFrame, players: pl.DataFrame
) -> pl.DataFrame:
    mine = teams.filter(pl.col("is_me")).select("league_id", "roster_id")
    return (
        rosters.join(mine, on=["league_id", "roster_id"])
        .join(id_map, on="sleeper_id", how="left")
        .join(players.select("sleeper_id", "full_name", "position"), on="sleeper_id", how="left")
        .with_columns(pl.col("position").fill_null("?"))
        .filter(pl.col("gsis_id").is_null() & (pl.col("position") != "DEF"))
        .select("league_id", "sleeper_id", "full_name", "position")
    )


def run() -> dict[str, int]:
    players = store.read_table("sleeper_players", "raw")
    overrides = pl.read_csv(
        OVERRIDES, schema={"sleeper_id": pl.String, "gsis_id": pl.String, "note": pl.String}
    )
    id_map = build_id_map(players, nfl.load_ff_playerids(), overrides)
    store.write_table("id_map", id_map)

    counts = dict(id_map.group_by("match_method").len().iter_rows())
    active = (
        players.filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position") != "DEF")
        .select("sleeper_id")
        .join(id_map.select("sleeper_id", "gsis_id"), on="sleeper_id")
    )
    counts["active_total"] = active.height
    counts["active_unmapped"] = active["gsis_id"].null_count()

    bad = unmapped_on_my_rosters(
        id_map,
        store.read_table("rosters", "raw"),
        store.read_table("league_teams", "raw"),
        players,
    )
    if bad.height:
        raise RuntimeError(
            f"{bad.height} players on your rosters have no nflverse ID. "
            f"Add them to {OVERRIDES}:\n{bad}"
        )
    return counts


def main() -> None:
    for key, value in sorted(run().items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
