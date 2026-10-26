"""Does the shipped source blend pick better lineups? Start/sit regret (`regret.py`) of ours
against the equal mean of ours and one outside source, on the weeks that source exists.

  (a) FFToday, scored as `prop_points.outside_points` ships it (league rules, plus the player's
      lagged fumble and two-point points, minus FFTODAY_BIAS): 2025 and 2026 weeks 1 to 6 (the
      cached pages; FFToday's top 50 per position). The bias was fit on 2025 weeks 1 to 6, so
      2025 is in sample for it.
  (b) Prop-implied points for RB and WR (`props_check.py` rows: FanDuel archive, a rushing-yards
      line for RB, receptions and receiving-yards lines for WR), 2024 weeks 2 to 17:
      `props_wf` with the walk-forward constants of props_check (earlier data only) and
      `props_shipped` with the shipped PROP_FIT (fit on 2024 to 2025, so in sample).
Rows without the source keep ours, as the production blend does. Sleeper's history is
re-stamped, so the four-way production mean cannot be scored. Ours is proj_learned (calibration
is skipped for the learned model); both roster constructions of regret.py, plus the real 2026
rosters in (a).

Rule (fixed before scoring): report only; flag "blend hurts decisions" if regret is worse in both
leagues with pooled weekly |t| >= 2 (per construction).

Third-party inputs are read in place, never copied into the repo:
  OMP_NUM_THREADS=3 uv run python research/blend_regret_check.py \
      --fftoday=<dir of FFToday pages> --props=<nfl-tools player_props/data dir>
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import polars as pl

ARGS = dict(a.split("=", 1) for a in sys.argv[1:])
sys.argv = sys.argv[:1]  # outside_history reads seasons from argv on import
sys.path.insert(0, str(Path(__file__).parent))
import fftoday_bias as fb  # noqa: E402
import outside_history as oh  # noqa: E402
import props_check as pc  # noqa: E402
import regret as r  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.stages import outside_projections as op  # noqa: E402
from fantasy.stages import prop_points as pp  # noqa: E402

KEY = r.KEY
PROP_POSITIONS = ("RB", "WR")


def fftoday_candidate(cache: Path) -> pl.DataFrame:
    oh.CACHE = cache
    mapped = op.map_to_gsis(oh.fftoday_rows(), op.people()).drop_nulls("gsis_id")
    parts = []
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        d = fb.rows(league, mapped)  # fftoday: league rules plus lagged unprojected points
        level = pl.col("position").replace_strict(pp.FFTODAY_BIAS, default=0.0)
        parts.append(
            d.select(
                pl.lit(league["league_id"]).alias("league_id"),
                "gsis_id",
                "season",
                "week",
                projection=(pl.col("ours") + pl.col("fftoday") - level) / 2,
            )
        )
    out = pl.concat(parts).unique(KEY)
    print(f"FFToday blend rows {out.height}")
    return out


def shipped_means(test_m: pl.DataFrame) -> pl.DataFrame:
    """props_check line rows with the shipped constants (prop_points.PROP_FIT)."""
    r_m = pl.col("market_key").replace_strict({m: v[0] for m, v in pp.PROP_FIT.items()})
    sigma = pl.col("market_key").replace_strict({m: v[1] for m, v in pp.PROP_FIT.items()})
    base = pl.when(pl.col("market_key") == "player_receptions").then(pl.col("lam"))
    return test_m.with_columns(prop_mean=r_m * base.otherwise(pl.col("line") + pl.col("z") * sigma))


def prop_candidates(archive: Path, uni: pl.DataFrame) -> dict[str, pl.DataFrame]:
    schedule = store.read_table("nfl_schedules", "raw")
    stats = store.read_table("nfl_player_stats", "raw")
    points = store.read_table("player_points")
    weights = {
        g["league_id"]: json.loads(g["scoring_settings"])
        for g in store.read_table("leagues", "raw").iter_rows(named=True)
    }
    abbr = pc.team_abbr(archive)
    test = pc.load_lines(archive / pc.TEST_FILE, abbr, schedule).filter(
        pl.col("season") == pc.TEST_SEASON
    )
    fit = pl.concat(
        [pc.load_lines(archive / f, abbr, schedule) for f in pc.FIT_FILES], how="diagonal_relaxed"
    ).filter(pl.col("season") == pc.FIT_SEASON)
    test_m = pc.with_raw_mean(pc.match_players(test, stats))
    wf, _ = pc.prop_means(test_m, pc.with_raw_mean(pc.match_players(fit, stats)))
    lags = pc.lagged_means(stats, points, weights)
    rows = uni.filter(pl.col("position").is_in(PROP_POSITIONS)).select(*KEY, "position", "learned")
    out = {}
    for name, means in (("props_wf", wf), ("props_shipped", shipped_means(test_m))):
        covered = pc.covered_rows(
            means.filter(pl.col("week") >= pc.FIRST_WEEK), rows, lags, weights
        )
        out[name] = covered.select(*KEY, projection=(pl.col("learned") + pl.col("f")) / 2).unique(
            KEY
        )
        print(f"{name}: covered rows {out[name].height}")
    return out


def score(
    weeks: dict[int, int], cands: dict[str, pl.DataFrame], real: bool, first_week: int = 1
) -> pl.DataFrame:
    r.LAST_WEEK = weeks
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        for name, frame in cands.items():
            files[name] = str(Path(tmp) / f"{name}.parquet")
            frame.write_parquet(files[name])
        uni, names = r.with_candidates(r.universe(), files)
    rosters = [r.built_rosters(c, uni) for c in r.CONSTRUCTIONS]
    if real:
        rosters.append(r.real_rosters())
    all_rosters = pl.concat(rosters, how="vertical_relaxed")
    r.self_check(uni, all_rosters)
    wk = r.weekly(r.score_rosters(all_rosters, uni, names), uni).filter(
        pl.col("week") >= first_week
    )
    return r.summary(wk)


def hurts(table: pl.DataFrame, cons: str) -> dict[str, str]:
    out = {}
    for (cand,), g in table.filter(pl.col("cons") == cons).group_by("cand"):
        if cand in (r.REF, "baseline"):
            continue
        worse = (g["d_regret"] < 0).all() and (g["t_regret"].abs() >= 2).any()
        out[cand] = "BLEND HURTS DECISIONS" if worse else "no"
    return out


def self_check() -> None:
    frame = pl.DataFrame(
        {
            "market_key": ["player_receptions", "player_rush_yds"],
            "lam": [4.0, np.nan],
            "line": [3.5, 50.0],
            "z": [0.0, 1.0],
        }
    )
    got = shipped_means(frame)["prop_mean"].to_list()
    rec, rush = pp.PROP_FIT["player_receptions"], pp.PROP_FIT["player_rush_yds"]
    assert np.allclose(got, [rec[0] * 4.0, rush[0] * (50.0 + rush[1])])


def main() -> None:
    self_check()
    cache = Path(ARGS.get("--fftoday", "research/scratch/fftoday"))
    archive = Path(ARGS.get("--props", str(pc.ARCHIVE)))
    cols = ["cons", "league", "cand", "weeks", "regret", "d_regret", "t_regret"]
    tail = ["band_rmse", "band_rmse_ref", "t_band", "rmse", "t_rmse"]

    print("\n===== (a) ours vs ours + FFToday, 2025 and 2026 weeks 1-6")
    a = score({2025: 6, 2026: 6}, {"ff_blend": fftoday_candidate(cache)}, real=True)
    print(a.select(*cols, "t_2025", "t_2026", *tail).sort("cons", "league", "cand"))
    for cons in ("A", "B", "real"):
        print(f"flag {cons}: {hurts(a, cons)}")

    print("\n===== (b) ours vs ours + prop points (RB, WR), 2024 weeks 2-17")
    r.LAST_WEEK = {2024: 17}
    props = prop_candidates(archive, r.with_candidates(r.universe(), {})[0])
    b = score({2024: 17}, props, real=False, first_week=pc.FIRST_WEEK)
    print(b.select(*cols, *tail).sort("cons", "league", "cand"))
    for cons in ("A", "B"):
        print(f"flag {cons}: {hurts(b, cons)}")


if __name__ == "__main__":
    main()
