"""DEF scoring against Sleeper: how many rostered DEF team-weeks match, and which differ.

`streaming.defense_points_frame` matched Sleeper in 52 of 60 (Colgate) and 41 of 60 (YinzBurgh)
DEF starter weeks (decisions.md, 2026-10-23). Tracing the misses through play-by-play
(2026-11-06) found four causes: yards allowed must be net of sack yards; nflverse `def_tds` count
interception returns only, so fumble-return TDs were missing (and stayed in the opponent's points
allowed); kick and punt return TDs must stay in points allowed; special-teams takeaways and forced
fumbles score at the `def_st_*` rates. Plus defensive two-point returns (YinzBurgh).

Compares the current scoring with the scoring as of main 50319c2e (`--old` reads it with git).
Every rostered DEF of the current season with a played game counts, bench included.

Run from the repo root: uv run python research/def_scoring_check.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy.stages import streaming
from fantasy.stages.crosswalk import TEAM_MAP

TOL = 0.011
OLD_COMMIT = "50319c2e"


def old_scorer():  # the pre-fix defense_points_frame, loaded from git
    source = subprocess.run(
        ["git", "show", f"{OLD_COMMIT}:src/fantasy/stages/streaming.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    path = Path(tempfile.mkdtemp()) / "streaming_old.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location("streaming_old", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.defense_points_frame


def main() -> None:
    games = store.read_table("team_games")
    stats = store.read_table("nfl_team_stats", "raw")
    leagues = store.read_table("leagues", "raw")
    mp = store.read_table("matchup_players", "raw")
    season = int(leagues["season"][0])
    stats = stats.filter(pl.col("season") == season)
    facts = streaming.load_play_facts(range(season, season + 1))
    old = old_scorer()
    for lg in leagues.iter_rows(named=True):
        scoring = json.loads(lg["scoring_settings"])
        new = streaming.defense_points_frame(stats, games, scoring, lg["league_id"], facts)
        before = old(stats, games, scoring, lg["league_id"])
        theirs = mp.filter(
            (pl.col("league_id") == lg["league_id"])
            & pl.col("sleeper_id").str.contains(r"^[A-Z]{2,3}$")
            & pl.col("points").is_not_null()
        ).select(
            pl.col("sleeper_id").replace(TEAM_MAP).alias("team"), "week", "is_starter",
            sleeper="points",
        )
        cmp = theirs.join(new.select("team", "week", "points"), on=["team", "week"]).join(
            before.select("team", "week", old="points"), on=["team", "week"]
        )
        for label, sub in (("rostered", cmp), ("starters", cmp.filter(pl.col("is_starter")))):
            for col in ("old", "points"):
                ok = int(((sub["sleeper"] - sub[col]).abs() <= TOL).sum())
                print(f"{lg['league_key']} {label} {'before' if col == 'old' else 'after'}: "
                      f"{ok} of {sub.height} exact")
        with pl.Config(tbl_rows=50):
            print(cmp.filter((pl.col("sleeper") - pl.col("points")).abs() > TOL).sort("week"))


if __name__ == "__main__":
    sys.exit(main())
