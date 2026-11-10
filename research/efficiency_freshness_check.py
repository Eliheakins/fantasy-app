"""Does building `nfl_team_efficiency` inside `streaming` (fresh) change K or DEF projections
compared with reading the previous refresh's copy (one refresh stale), as the pipeline did before
the environment stage was removed (2026-11-10)?

Variants of the table fed to `streaming_model.team_trailing`:
- fresh: rebuilt from play-by-play now (the new behavior);
- stale: fresh without the latest played week (what the first run after a week's games read);
- empty: no rows at all.
Each league's DEF and K projections and walk-forward RMSE (scored 2024 on) are compared across
variants. Ship rule, written before the run: ships if all are identical, or if fresh beats stale
with a paired per-week t of -2 or lower.

Run from the repo root after `make refresh`: uv run python research/efficiency_freshness_check.py
Reads only; writes nothing (the stage's own table write is replaced).
"""

import dataclasses
import json

import polars as pl
from polars.testing import assert_frame_equal

from fantasy import store
from fantasy.stages import streaming as st
from fantasy.stages import streaming_model as sm
from nfl_stat.core.seasons import FANTASY_FIRST_SEASON

KEY = ["team", "season", "week"]


def variants(last_season: int) -> dict[str, pl.DataFrame]:
    columns = list(store.SCHEMAS["nfl_team_efficiency"])
    fresh = st.team_efficiency(range(FANTASY_FIRST_SEASON, last_season + 1)).select(columns)
    latest = fresh.sort("season", "week").select("season", "week").row(-1, named=True)
    stale = fresh.filter(~((pl.col("season") == latest["season"]) & (pl.col("week") == latest["week"])))
    # the test only means something if the stale table really lacks rows the fresh one has
    assert stale.height < fresh.height, "no latest week to drop"
    print(f"fresh {fresh.height} rows through {latest['season']} week {latest['week']}; stale {stale.height}")
    return {"fresh": fresh, "stale": stale, "empty": fresh.head(0)}


def league_results(data: st.Inputs) -> dict[str, tuple[pl.DataFrame, tuple[float, float]]]:
    out = {}
    for lg in data.leagues.iter_rows(named=True):
        lid, current = lg["league_id"], int(lg["current_week"])
        points = st.defense_points_frame(
            data.stats, data.games, json.loads(lg["scoring_settings"]), lid, data.facts
        ).filter(pl.col("season") >= st.SCORED_FROM)
        season = int(points["season"].to_numpy().max())
        out[f"{lg['league_key']} DEF"] = st._def_projection(data, points, season, current, lid)
        out[f"{lg['league_key']} K"] = st._k_projection(data, season, current, lid)
    return out


def main() -> None:
    stats = store.read_table("nfl_team_stats", "raw")
    tables = variants(int(stats["season"].max()))  # type: ignore[arg-type]
    st.load_efficiency = lambda season: tables["fresh"]  # no table write
    base = st._load_inputs()
    pace = store.read_table("nfl_team_pace", "raw")

    results, teams = {}, {}
    for name, table in tables.items():
        teams[name] = sm.team_trailing(base.stats, table, pace, base.coded)
        results[name] = league_results(dataclasses.replace(base, teams=teams[name]))

    efficiency = [f"{c}_tr" for c in sm.TEAM_EFFICIENCY]
    differs = teams["fresh"].select(efficiency).equals(teams["stale"].select(efficiency))
    print(f"trailed efficiency columns differ between fresh and stale: {not differs}")
    used = [c for c in teams["fresh"].columns if c not in efficiency]
    for name in ("stale", "empty"):
        assert_frame_equal(teams["fresh"].select(used), teams[name].select(used), check_exact=True)
    print("every other trailed team column is identical across variants")

    # the walk-forward sums errors in group_by order, so identical inputs can differ in the last bits
    print(f"{'unit':<16}{'fresh rmse (model, mean)':<30}{'|gap| stale':<14}{'|gap| empty':<14}")
    for unit, (proj, rmse) in results["fresh"].items():
        same = {}
        for name in ("stale", "empty"):
            other_proj, other_rmse = results[name][unit]
            assert_frame_equal(proj, other_proj, check_exact=True)
            gap = max(abs(a - b) for a, b in zip(rmse, other_rmse, strict=True))
            same[name] = f"{gap:.0e}"
        print(f"{unit:<16}{f'({rmse[0]:.4f}, {rmse[1]:.4f})':<30}{same['stale']:<14}{same['empty']:<14}")
    print("projections exactly identical across variants: the efficiency table feeds no K or DEF feature")


if __name__ == "__main__":
    main()
