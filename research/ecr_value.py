"""Do FantasyPros weekly expert rankings (nflverse `load_ff_rankings`) improve the learned model?

The archive keeps about one weekly position ranking a week from 2020 on (type `wp`, average expert rank
at the position with spread, best and worst) and an overall ranking (`wo`). Each scrape is matched to the
next game week and the last scrape before that week's first game is used, so the ranking is what an
expert panel believed before kickoff. Training and scoring use 2020 to 2023 and 2024 to 2025 (the
archive does not reach further back), the base model being the one in data_value.py trained on the same
rows, so the comparison is like for like.

For private local use only: the data belongs to FantasyPros and is not committed or redistributed.

scikit-learn is not a project dependency. Run from the repo root:
    uv run --with scikit-learn python research/ecr_value.py
"""

import sys

import nflreadpy as nfl
import numpy as np
import polars as pl

sys.path.insert(0, "research")
import data_value as dv  # noqa: E402

MAX_GAP_DAYS = 9  # a scrape counts for a week only if it falls this close before the week's first game


def week_calendar() -> pl.DataFrame:
    """First game date of every regular-season week."""
    s = nfl.load_schedules(seasons=dv.SEASONS).filter(pl.col("game_type") == "REG")
    return (
        s.with_columns(pl.col("gameday").str.to_date().alias("first_game"))
        .group_by("season", "week")
        .agg(pl.col("first_game").min())
        .sort("first_game")
    )


def ranking_features() -> pl.DataFrame:
    ids = nfl.load_ff_playerids().select(pl.col("fantasypros_id").cast(pl.String).alias("id"), "gsis_id").drop_nulls().unique("id")
    cal = week_calendar()
    allrk = nfl.load_ff_rankings(type="all")
    out = []
    for kind, prefix in (("wp", "ecr_pos"), ("wo", "ecr_all")):
        rk = allrk.filter(pl.col("ecr_type") == kind)
        rk = rk.with_columns(pl.col("scrape_date").str.to_date().alias("scraped"), pl.col("id").cast(pl.String)).sort("scraped")
        scrapes = rk.select("scraped").unique().sort("scraped")
        matched = scrapes.join_asof(cal, left_on="scraped", right_on="first_game", strategy="forward").filter(
            (pl.col("first_game") - pl.col("scraped")).dt.total_days() <= MAX_GAP_DAYS
        )
        # the last scrape before each week's first game
        latest = matched.group_by("season", "week").agg(pl.col("scraped").last())
        keep = latest.join(matched, on=["season", "week", "scraped"])
        rows = rk.join(keep, on="scraped").join(ids, on="id")
        out.append(
            rows.select(
                "gsis_id", pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32),
                pl.col("ecr").cast(pl.Float64).alias(prefix),
                pl.col("sd").cast(pl.Float64).alias(f"{prefix}_sd"),
                (pl.col("worst") - pl.col("best")).cast(pl.Float64).alias(f"{prefix}_range"),
            ).unique(dv.KEY, keep="first")
        )
    return out[0].join(out[1], on=dv.KEY, how="full", coalesce=True)


def main() -> None:
    d, feats = dv.base_frame()
    d = d.filter(pl.col("season") >= 2020)
    ecr = ranking_features()
    cols = [c for c in ecr.columns if c not in dv.KEY]
    de = d.join(ecr, on=dv.KEY, how="left")
    covered = float(de.filter(pl.col("season") >= 2024)["ecr_pos"].is_not_null().mean())
    print(f"rows with a position ranking in 2024-2025: {covered:.1%}")
    base = dv.fit_predict(d, feats)
    rmse = lambda f: float(np.sqrt(((f["points"] - f["pred"]) ** 2).mean()))  # noqa: E731
    print(f"base (2020-2023 training): RMSE {rmse(base):.4f}; our rolling baseline "
          f"{float(np.sqrt(((base['points'] - base['ours']) ** 2).mean())):.4f}")
    results = [dv.compare("expert rankings", base, dv.fit_predict(de, feats + cols))]

    # the same, on top of every free dataset from data_value.py
    r, w, pace = dv.roster_features(), dv.weather_features(), dv.team_pace()
    rf = ["age", "years_exp", "draft_pick", "roster_active", "weight"]
    wf = ["temp", "wind", "div_game", "rest", "indoor", "moneyline"]
    pf = [c for c in pace.columns if c.startswith("pace_")]
    rich = d.join(r, on=dv.KEY, how="left").join(w, on=["season", "week", "team"], how="left").join(pace, on=["team", "season", "week"], how="left")
    depth = dv.depth_features().unique(dv.KEY)
    rich = rich.join(depth, on=dv.KEY, how="left")
    af = []
    for table, tcols in dv.advanced_tables():
        rich = dv.lag_asof(rich, table.unique(dv.KEY), "gsis_id", tcols)
        af += [f"adv_{c}" for c in tcols]
    free = feats + rf + wf + pf + af + ["depth_rank"]
    rich_base = dv.fit_predict(rich, free)
    print(f"free datasets only: RMSE {rmse(rich_base):.4f}")
    results.append(dv.compare("free data + rankings", rich_base, dv.fit_predict(rich.join(ecr, on=dv.KEY, how="left"), free + cols)))
    with pl.Config(tbl_rows=10, tbl_cols=14, tbl_width_chars=170):
        print(pl.DataFrame(results))

    # how good is the ranking alone? rank correlation with the points actually scored
    j = de.filter((pl.col("season") >= 2024) & pl.col("ecr_pos").is_not_null())
    for pos in ("QB", "RB", "WR", "TE"):
        g = j.filter(pl.col("position") == pos)
        print(pos, "Spearman(rank, points)", round(float(g.select(pl.corr("ecr_pos", "points", method="spearman")).item()), 3),
              " Spearman(our projection, points)", round(float(g.select(pl.corr("ours", "points", method="spearman")).item()), 3))


if __name__ == "__main__":
    main()
