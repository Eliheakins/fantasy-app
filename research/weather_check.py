# Issue #48 step 1: does actual game weather (temperature, wind) add held-out accuracy to the
# learned model on its own, by position?
#
# The learned model (fantasy.stages.learn) is walk-forward fit on earlier seasons and scored on
# 2024 onward. The variants add the game own temperature and/or wind to its design matrix. Weather
# is known for a played game (actual) and for the next game only as a forecast, so a positive
# result here still needs a forecast archive (step 2). Nulls: indoor games (dome/closed roof) get a
# neutral temperature (NEUTRAL_TEMP) and no wind; outdoor games with null weather get the outdoor
# median and a wx_missing flag. A random-noise column is a placebo for the noise floor.
#
# Reads data/ only; writes only to OUT_DIR. Run: uv run python research/weather_check.py

from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages import learn
from fantasy.stages.project import GROUP, expected_frame

OUT_DIR = Path(
    "/private/tmp/claude-501/-Users-eliheakins-personal-fantasy-app/"
    "6d05dc3b-e164-4d13-8e8d-01dfa4a4ab56/scratchpad/weather"
)
NEUTRAL_TEMP = 70.0
FIRST_SCORED = 2024
MIN_PROJECTION = learn.MIN_PROJECTION
KEY = [*GROUP, "season", "week"]
VARIANTS = {
    "temp": ["wx_temp"],
    "wind": ["wx_wind"],
    "temp+wind": ["wx_temp", "wx_wind", "wx_missing"],
    "placebo": ["wx_noise"],
}


def missingness(sched: pl.DataFrame) -> None:
    # split null weather into future (unplayed), indoor, and outdoor games with a real gap
    s = sched.with_columns(
        pl.when(pl.col("home_score").is_null())
        .then(pl.lit("future"))
        .when(pl.col("roof").is_in(["dome", "closed"]))
        .then(pl.lit("indoor"))
        .when(pl.col("roof").is_null())
        .then(pl.lit("roof unknown"))
        .otherwise(pl.lit("outdoor/open"))
        .alias("kind"),
        pl.col("temp").is_null().alias("null"),
    )
    print("weather nulls by kind (all games in nfl_schedules):")
    print(s.group_by("kind").agg(pl.len(), pl.col("null").sum().alias("null_wx")).sort("kind"))
    print(f"total games {s.height}, null weather {int(s["null"].sum())} ({100 * s["null"].mean():.1f}%)")
    per = (
        s.filter(pl.col("kind") == "outdoor/open")
        .group_by("season")
        .agg(pl.len().alias("outdoor"), pl.col("null").sum().alias("null"))
        .sort("season")
    )
    print("outdoor/open played games with null weather by season:")
    print(per)


def team_weather(sched: pl.DataFrame, seed: int = 0) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    indoor = pl.col("roof").is_in(["dome", "closed"])
    ref = sched.filter(~indoor & (pl.col("season") <= 2023))
    w = sched.select(
        "season",
        "week",
        "home_team",
        "away_team",
        pl.when(indoor)
        .then(NEUTRAL_TEMP)
        .otherwise(pl.col("temp").fill_null(ref["temp"].median()))
        .alias("wx_temp"),
        pl.when(indoor)
        .then(0.0)
        .otherwise(pl.col("wind").fill_null(ref["wind"].median()))
        .alias("wx_wind"),
        (~indoor & pl.col("temp").is_null()).cast(pl.Float64).alias("wx_missing"),
    )
    cols = ["season", "week", "wx_temp", "wx_wind", "wx_missing"]
    both = pl.concat(
        [
            w.select(pl.col("home_team").alias("team"), *cols),
            w.select(pl.col("away_team").alias("team"), *cols),
        ]
    ).unique(["season", "week", "team"], keep="first", maintain_order=True)
    return both.with_columns(pl.Series("wx_noise", rng.normal(size=both.height)))


def compare(d: pl.DataFrame, name: str, label: str) -> dict:
    # d has se_base and se_<name>; paired by week; a positive gain means the variant is better
    by_week = d.group_by("season", "week").agg(pl.col("se_base").mean(), pl.col(f"se_{name}").mean())
    diff = (by_week["se_base"] - by_week[f"se_{name}"]).to_numpy()
    rb = float(np.sqrt(d["se_base"].mean()))
    rv = float(np.sqrt(d[f"se_{name}"].mean()))
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else float("nan")
    return {
        "group": label,
        "variant": name,
        "n": d.height,
        "rmse_base": round(rb, 4),
        "rmse_variant": round(rv, 4),
        "gain_pct": round(100 * (rb - rv) / rb, 2),
        "t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sched = store.read_table("nfl_schedules", "raw")
    missingness(sched)
    weather = team_weather(sched)

    leagues = store.read_table("leagues", "raw")
    league_id = sorted(leagues["league_id"].to_list())[0]  # weather is league-independent
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = learn.games_frame(
        exp, opp, store.read_table("nfl_snaps", "raw"), store.read_table("nfl_player_stats", "raw")
    )
    games = games_all.filter(pl.col("league_id") == league_id)
    targets = learn.history_targets(exp.filter(pl.col("league_id") == league_id))
    features = learn.build_features(
        targets, learn.state_frame(games), store.read_table("team_games"), learn.load_extras()
    )
    history = features.join(games.select(*GROUP, "season", "week", "points"), on=KEY).join(
        weather, on=["season", "week", "team"], how="left"
    )
    print(f"league {league_id}: {history.height} player-games, "
          f"weather null after join: {history["wx_temp"].null_count()}")

    base_features = list(learn.EXTRA_FEATURES)
    base = learn.walk_forward(history)
    out = base.select(*KEY, "position", "team", "points", pl.col("projection").alias("base"))
    for name, cols in VARIANTS.items():
        learn.EXTRA_FEATURES = base_features + cols  # design() reads the module global
        try:
            run = learn.walk_forward(history)
        finally:
            learn.EXTRA_FEATURES = base_features
        out = out.join(run.select(*KEY, pl.col("projection").alias(name)), on=KEY)
    out = out.join(
        weather.select("season", "week", "team", "wx_wind", "wx_temp"),
        on=["season", "week", "team"],
        how="left",
    )
    out.write_parquet(OUT_DIR / "weather_predictions.parquet")

    d = out.filter((pl.col("season") >= FIRST_SCORED) & (pl.col("base") > MIN_PROJECTION))
    for col in ("base", *VARIANTS):
        d = d.with_columns(((pl.col("points") - pl.col(col)) ** 2).alias(f"se_{col}"))
    rows = []
    for name in VARIANTS:
        rows.append(compare(d, name, "ALL"))
        for pos in ("QB", "RB", "WR", "TE", "K"):
            sub = d.filter(pl.col("position") == pos)
            if sub.height > 200:
                rows.append(compare(sub, name, pos))
        rows.append(compare(d.filter(pl.col("wx_wind") >= 15), name, "wind>=15mph"))
        rows.append(compare(d.filter(pl.col("wx_temp") <= 32), name, "temp<=32F"))
    res = pl.DataFrame(rows)
    res.write_csv(OUT_DIR / "weather_results.csv")
    with pl.Config(tbl_rows=100, tbl_cols=12, tbl_width_chars=170):
        print(res)


if __name__ == "__main__":
    main()
