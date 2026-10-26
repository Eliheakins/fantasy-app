"""Do pre-kickoff news flags predict the shipped blend's miss? (run about week 16)

News source: day-over-day changes in the Sleeper status archive (`sleeper_player_status`, written
by the news_archive stage). RotoWire's RSS was the planned text source, but its terms forbid
archiving it (Article VI, checked 2026-10-26), so no text is tagged. Flags, per player:
  out:       injury status newly Out, IR, Sus or PUP
  role_up:   depth chart order becomes 1 from 2 or lower, same team
  role_down: depth chart order leaves 1 for 2 or lower on the same team, or the team becomes empty
  capped:    no Sleeper field says it, so not tested (needs a text source)
A player's first snapshot has nothing to compare with, so it flags nothing. A flag counts for a
game when the snapshot that first shows it was fetched in the WINDOW before that team's kickoff.

Rows: `blend_weight.league_rows` (our last snapshot before kickoff, calibrated, paired with
Sleeper, FFToday and props as fetched before kickoff), residual = actual - the shipped blend (the
equal-weight mean of every source a row has, a Questionable or Doubtful Sleeper 0 left out).
Test per flag and position: each week, mean residual of flagged rows minus that of the others,
paired t over weeks (weeks with both groups, at least MIN_WEEKS). Placebo: flags shuffled within
position-week N_PLACEBO times; p = share of placebo |t| at least the real |t|. A flag is worth a
layer only with |t| >= 2 and placebo p < 0.05, and then still needs the held-out test in CLAUDE.md.
The two leagues score the same games: read their results as one test.

Run from the repo root: uv run python research/news_residual_check.py
"""

from datetime import timedelta

import numpy as np
import polars as pl

from blend_weight import league_rows
from fantasy import store
from fantasy._scorecard import KEY, _at, _kickoff_frame
from fantasy.stages.simulate import SLEEPER_ZEROED_STATUSES

WINDOW = timedelta(days=6)  # shortcut: a fixed window, not "since the player's last game"
OUT_STATUSES = ("Out", "IR", "Sus", "PUP")
TAGS = ("out", "role_up", "role_down")
MIN_WEEKS = 3
N_PLACEBO = 200
T_RULE, P_RULE = 2.0, 0.05


def sleeper_events(snaps: pl.DataFrame) -> pl.DataFrame:
    """sleeper_id, at (datetime), tag for each change between a player's consecutive snapshots."""
    prev = {c: pl.col(c).shift().over("sleeper_id") for c in ("team", "injury_status", "depth_chart_order", "fetched_at")}
    order = pl.col("depth_chart_order")
    same_team = pl.col("team").eq_missing(pl.col("_team"))
    flags = (
        snaps.sort("sleeper_id", "fetched_at")
        .with_columns(**{f"_{k}": v for k, v in prev.items()})
        .filter(pl.col("_fetched_at").is_not_null())
        .with_columns(
            out=pl.col("injury_status").is_in(OUT_STATUSES) & pl.col("injury_status").ne_missing(pl.col("_injury_status")),
            role_up=(order == 1) & (pl.col("_depth_chart_order") > 1) & same_team,
            role_down=((pl.col("_depth_chart_order") == 1) & (order > 1) & same_team)
            | (pl.col("team").is_null() & pl.col("_team").is_not_null()),
        )
    )
    return (
        flags.unpivot(TAGS, index=["sleeper_id", "fetched_at"], variable_name="tag")
        .filter(pl.col("value").fill_null(False))
        .select("sleeper_id", _at().alias("at"), "tag")
    )


def flag_rows(rows: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    """rows (KEY, kickoff, ...) with a boolean column per tag: an event in WINDOW before kickoff."""
    hits = (
        rows.select(*KEY, "kickoff")
        .join(events, on="gsis_id")
        .filter((pl.col("at") < pl.col("kickoff")) & (pl.col("at") >= pl.col("kickoff") - WINDOW))
        .select(*KEY, "tag")
        .unique()
        .with_columns(pl.lit(True).alias("hit"))
    )
    out = rows
    for tag in TAGS:
        mine = hits.filter(pl.col("tag") == tag).select(*KEY, pl.col("hit").alias(tag))
        out = out.join(mine, on=KEY, how="left").with_columns(pl.col(tag).fill_null(False))
    return out


def weekly_t(d: pl.DataFrame, flag: str) -> tuple[float, int, float]:
    """d: season, week, resid, `flag`. Paired t over weeks of the flagged-minus-other mean residual,
    the weeks used and the mean difference (nan when fewer than MIN_WEEKS weeks)."""
    by = (
        d.group_by("season", "week")
        .agg(
            pl.col("resid").filter(pl.col(flag)).mean().alias("a"),
            pl.col("resid").filter(~pl.col(flag)).mean().alias("b"),
        )
        .drop_nulls()
    )
    diff = (by["a"] - by["b"]).to_numpy()
    if len(diff) < MIN_WEEKS or diff.std(ddof=1) == 0:
        return float("nan"), len(diff), float(diff.mean()) if len(diff) else float("nan")
    return float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))), len(diff), float(diff.mean())


def test_flag(d: pl.DataFrame, flag: str, n_placebo: int = N_PLACEBO) -> dict[str, float | int | str]:
    """One position's rows: the real t and the placebo p (flags shuffled within week)."""
    t, weeks, gap = weekly_t(d, flag)
    p = float("nan")
    if not np.isnan(t):
        placebo = [
            weekly_t(d.with_columns(pl.col(flag).shuffle(seed=s).over("season", "week")), flag)[0]
            for s in range(n_placebo)
        ]
        p = float(np.mean(np.abs(np.nan_to_num(placebo)) >= abs(t)))
    keep = not np.isnan(t) and abs(t) >= T_RULE and p < P_RULE
    return {
        "n_flagged": int(d[flag].sum()), "weeks": weeks, "mean_gap": round(gap, 2),
        "t": round(t, 2), "placebo_p": round(p, 3), "verdict": "signal" if keep else "none",
    }


def report(rows: pl.DataFrame, n_placebo: int = N_PLACEBO) -> pl.DataFrame:
    out = []
    for tag in TAGS:
        for (pos,), d in rows.group_by("position"):
            if d[tag].any():
                out.append({"tag": tag, "position": pos, **test_flag(d, tag, n_placebo)})
    return pl.DataFrame(out).sort("tag", "position") if out else pl.DataFrame()


def self_check() -> None:
    """Events: a promotion, a newly-Out player, a release; first snapshots flag nothing; a later
    event does not flag an earlier game. Test: a known RB effect is found, no WR effect is not."""
    day = ["2026-10-20T15:00:00+00:00", "2026-10-21T15:00:00+00:00"]
    snap = pl.DataFrame(
        {
            "sleeper_id": ["a", "a", "b", "b", "c", "c"], "fetched_at": day * 3,
            "team": ["KC", "KC", "BUF", "BUF", "NYJ", None], "injury_status": [None, None, "Questionable", "Out", None, None],
            "depth_chart_order": [2, 1, 1, 1, 1, None],
        }
    )
    ev = sleeper_events(snap)
    assert sorted(zip(ev["sleeper_id"], ev["tag"])) == [("a", "role_up"), ("b", "out"), ("c", "role_down")], ev
    kick = pl.Series(["2026-10-22T17:00:00", "2026-10-21T12:00:00"]).str.to_datetime(time_zone="UTC", time_unit="us")
    games = pl.DataFrame({"league_id": "L", "gsis_id": "a", "season": 2026, "week": [8, 7], "kickoff": kick})
    flagged = flag_rows(games, ev.with_columns(gsis_id=pl.col("sleeper_id")))
    assert flagged.sort("week")["role_up"].to_list() == [False, True]  # the event came after week 7's kickoff

    rng = np.random.default_rng(1)  # seed 0 draws a 2.5-se noise gap for WR by chance
    n = 8 * 600
    d = pl.DataFrame(
        {
            "season": 2026, "week": np.repeat(np.arange(1, 9), 600), "position": np.tile(["RB", "WR"], n // 2),
            "role_up": rng.random(n) < 0.1,
        }
    )
    d = d.with_columns(
        resid=pl.Series(rng.normal(0, 6, n)) + pl.when(pl.col("role_up") & (pl.col("position") == "RB")).then(3.0).otherwise(0.0)
    ).with_columns(out=pl.lit(False), role_down=pl.lit(False))
    res = {r["position"]: r for r in report(d, n_placebo=50).iter_rows(named=True)}
    assert res["RB"]["verdict"] == "signal" and res["RB"]["t"] > 2, res
    assert res["WR"]["verdict"] == "none", res
    print("self-check passed")


def league_panel(league: dict, events: pl.DataFrame, id_map: pl.DataFrame) -> pl.DataFrame:
    scored = league_rows(league)[0]
    sources = [c for c in ("fftoday", "props") if c in scored.columns]
    zeroed = pl.col("status").is_in(list(SLEEPER_ZEROED_STATUSES)) & (pl.col("sleeper") == 0)
    rows = (
        scored.filter(pl.col("ours").is_not_null())
        .with_columns(pl.when(zeroed).then(None).otherwise(pl.col("sleeper")).alias("sleeper"))
        .with_columns(resid=pl.col("actual") - pl.mean_horizontal("ours", "sleeper", *sources))
    )
    kick = _kickoff_frame(rows.select(*KEY, "team"), store.read_table("nfl_schedules", "raw"))
    rows = rows.join(kick, on=["season", "week", "team"])
    return flag_rows(rows, events.join(id_map, on="sleeper_id"))


def main() -> None:
    self_check()
    try:
        snaps = store.read_table("sleeper_player_status", "archive")
    except FileNotFoundError:
        print("no sleeper_player_status archive yet: run the news_archive stage (make refresh)")
        return
    events = sleeper_events(snaps)
    days = snaps["fetched_at"].str.slice(0, 10).n_unique()
    print(f"archive: {snaps.height} rows, {days} days; events by tag: "
          f"{dict(events.group_by('tag').len().iter_rows())}")
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id")
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        panel = league_panel(league, events, id_map)
        flagged = {t: int(panel[t].sum()) for t in TAGS}
        print(f"\n=== {league['name']}: {panel.height} player-games, "
              f"weeks {sorted(panel.select('season', 'week').unique().rows())}, flagged {flagged}")
        result = report(panel)
        print(result if result.height else "nothing to test yet (no flagged player-games)")
    print("\nThe two leagues score the same games: read their results as one test.")


if __name__ == "__main__":
    main()
