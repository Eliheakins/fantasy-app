"""Which free nflverse datasets add held-out accuracy to a learned player model?

Starts from the boosted model in gbm_test.py (lagged points, expected points, volume, snap and target
share, implied total, practice flags) and adds one dataset's pre-game features at a time:

  roster    age, years in the league, draft pick, roster status (rosters_weekly)
  weather   roof, temperature, wind, rest days, division game (schedules)
  advanced  Pro-Football-Reference and Next Gen Stats efficiency, lagged
  pace      team plays, dropbacks and pass rate over expected, lagged (play by play)

Every feature uses only games before the one being projected. Train on 2019 to 2023, score 2024 to
2025 (our size-calibrated baseline above 3 points), report the change in RMSE with a paired
per-week t-statistic (positive means better than the base model).

scikit-learn is not a project dependency. Run from the repo root:
    uv run --with scikit-learn python research/data_value.py
"""

import datetime as dt

import nflreadpy as nfl
import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame

TRAIN_END = 2023
SEASONS = list(range(2018, 2027))
LAG_COLS = ["points", "exp_pts", "tgt", "car", "att", "snap", "tshare", "rec_touchdown_exp", "rush_touchdown_exp"]
HALF_LIVES = (2, 4, 8)
EWM_HL = 4
KEY = ["gsis_id", "season", "week"]


def lags() -> list[pl.Expr]:
    out = []
    for c in LAG_COLS:
        out += [pl.col(c).ewm_mean(half_life=h).shift(1).over("gsis_id").alias(f"{c}_hl{h}") for h in HALF_LIVES]
        out.append(pl.col(c).shift(1).over("gsis_id").alias(f"{c}_last"))
    return out


def base_frame() -> tuple[pl.DataFrame, list[str]]:
    """One row per played player-week with the base lagged features, our projection and the points."""
    lid = store.read_table("leagues", "raw").sort("league_key")["league_id"][0]
    history = store.read_table("proj_baseline").filter(
        (pl.col("league_id") == lid) & ~pl.col("is_future") & pl.col("has_history")
    )
    res = residual_frame(store.read_table("proj_baseline"), store.read_table("player_points"))
    curves = estimate_curves(res.filter((pl.col("league_id") == lid) & (pl.col("season") <= TRAIN_END)))
    ours = apply_curves(history, curves).select("gsis_id", "season", "week", "position", pl.col("projection").alias("ours"))
    pts = store.read_table("player_points").filter(pl.col("league_id") == lid)
    games = pts.select("gsis_id", "season", "week", "points", "team", "team_implied", "total_line", "is_home").sort(*KEY)
    opp = store.read_table("nfl_ff_opportunity", "raw").select(
        pl.col("player_id").alias("gsis_id"), "season", "week",
        pl.col("total_fantasy_points_exp").alias("exp_pts"), pl.col("rec_attempt").alias("tgt"),
        pl.col("rush_attempt").alias("car"), pl.col("pass_attempt").alias("att"),
        "rec_touchdown_exp", "rush_touchdown_exp",
    )
    snaps = (
        store.read_table("nfl_snaps", "raw").filter(pl.col("gsis_id").is_not_null())
        .select(*KEY, pl.col("offense_pct").alias("snap")).unique(KEY)
    )
    stats = (
        store.read_table("nfl_player_stats", "raw").filter(pl.col("season_type") == "REG")
        .select(pl.col("player_id").alias("gsis_id"), "season", "week", pl.col("target_share").alias("tshare"))
        .unique(KEY)
    )
    inj = (
        store.read_table("nfl_injuries", "raw").filter(pl.col("game_type") == "REG").unique(KEY, keep="first")
        .select(
            *KEY,
            (pl.col("report_status") == "Questionable").fill_null(False).cast(pl.Float64).alias("inj_q"),
            (pl.col("report_status") == "Doubtful").fill_null(False).cast(pl.Float64).alias("inj_d"),
            pl.col("practice_status").str.contains("Did Not|DNP").fill_null(False).cast(pl.Float64).alias("prac_dnp"),
            pl.col("practice_status").str.contains("Limited").fill_null(False).cast(pl.Float64).alias("prac_lim"),
        )
    )
    g = (
        games.join(opp, on=KEY, how="left").join(snaps, on=KEY, how="left").join(stats, on=KEY, how="left")
        .sort(*KEY).with_columns(lags())
    )
    g = g.with_columns(
        pl.col("points").cum_count().over("gsis_id").alias("n_games"),
        pl.col("points").rolling_std(8, min_samples=3).shift(1).over("gsis_id").alias("pts_sd8"),
        pl.col("is_home").cast(pl.Float64),
    ).join(inj, on=KEY, how="left").with_columns(pl.col(["inj_q", "inj_d", "prac_dnp", "prac_lim"]).fill_null(0.0))
    d = g.join(ours, on=KEY, how="inner").with_columns(
        *[(pl.col("position") == p).cast(pl.Float64).alias(f"is_{p.lower()}") for p in ("QB", "RB", "WR")]
    )
    feats = [c for c in d.columns if any(c.startswith(f"{x}_") for x in LAG_COLS)] + [
        "n_games", "pts_sd8", "team_implied", "total_line", "is_home", "is_qb", "is_rb", "is_wr", "week",
        "inj_q", "inj_d", "prac_dnp", "prac_lim",
    ]
    return d, feats


def roster_features() -> pl.DataFrame:
    r = nfl.load_rosters_weekly(seasons=SEASONS).filter(pl.col("game_type") == "REG")
    r = r.filter(pl.col("gsis_id").is_not_null()).unique(KEY, keep="first")
    start = pl.col("season").map_elements(lambda s: dt.date(s, 9, 1), return_dtype=pl.Date)
    return r.select(
        *KEY,
        ((start - pl.col("birth_date")).dt.total_days() / 365.25).alias("age"),
        pl.col("years_exp").cast(pl.Float64).alias("years_exp"),
        pl.col("draft_number").cast(pl.Float64).fill_null(300.0).alias("draft_pick"),
        (pl.col("status") == "ACT").cast(pl.Float64).alias("roster_active"),
        pl.col("weight").cast(pl.Float64),
    )


def weather_features() -> pl.DataFrame:
    s = nfl.load_schedules(seasons=SEASONS).filter(pl.col("game_type") == "REG")
    common = ["season", "week", "temp", "wind", "div_game", "roof"]
    home = s.select(*common, pl.col("home_team").alias("team"), pl.col("home_rest").alias("rest"), pl.col("home_moneyline").alias("moneyline"))
    away = s.select(*common, pl.col("away_team").alias("team"), pl.col("away_rest").alias("rest"), pl.col("away_moneyline").alias("moneyline"))
    return pl.concat([home, away]).select(
        "season", "week", "team",
        pl.col("temp").cast(pl.Float64), pl.col("wind").cast(pl.Float64),
        pl.col("div_game").cast(pl.Float64), pl.col("rest").cast(pl.Float64),
        pl.col("roof").is_in(["dome", "closed"]).cast(pl.Float64).alias("indoor"),
        pl.col("moneyline").cast(pl.Float64),
    )


def lag_asof(target: pl.DataFrame, table: pl.DataFrame, by: str, cols: list[str]) -> pl.DataFrame:
    """Join each column's weighted average over the rows strictly before the target game."""
    t = table.sort(by, "season", "week").with_columns(
        *[pl.col(c).ewm_mean(half_life=EWM_HL).over(by).alias(f"adv_{c}") for c in cols],
        (pl.col("season") * 100 + pl.col("week")).alias("t"),
    ).select(by, "t", *[f"adv_{c}" for c in cols])
    left = target.with_columns((pl.col("season") * 100 + pl.col("week")).alias("t")).sort("t")
    return left.join_asof(t.sort("t"), on="t", by=by, strategy="backward", allow_exact_matches=False).drop("t")


def advanced_tables() -> list[tuple[pl.DataFrame, list[str]]]:
    """Per-player advanced stats keyed by gsis_id, one row per player-week, columns prefixed by source."""
    ids = nfl.load_ff_playerids().select("pfr_id", "gsis_id").drop_nulls().unique("pfr_id")
    pfr = nfl.load_pfr_advstats(seasons=[s for s in SEASONS if s >= 2018], stat_type="rec", summary_level="week")
    pfr = pfr.filter(pl.col("game_type") == "REG").join(ids, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    pfr_cols = ["rushing_broken_tackles", "receiving_broken_tackles", "receiving_drop_pct", "receiving_rat"]
    pfr = pfr.select("gsis_id", "season", "week", *[pl.col(c).cast(pl.Float64).alias(f"pfr_{c}") for c in pfr_cols])
    frames = [(pfr, [f"pfr_{c}" for c in pfr_cols])]
    skip = {"season", "season_type", "week", "player_display_name", "player_position", "team_abbr", "player_gsis_id",
            "player_first_name", "player_last_name", "player_jersey_number", "player_short_name"}
    for kind in ("receiving", "rushing", "passing"):
        n = nfl.load_nextgen_stats(seasons=SEASONS, stat_type=kind).filter(pl.col("week") > 0)
        num = [c for c, t in n.schema.items() if c not in skip and t.is_numeric()]
        n = n.select(pl.col("player_gsis_id").alias("gsis_id"), "season", "week", *[pl.col(c).cast(pl.Float64).alias(f"ngs{kind[:3]}_{c}") for c in num])
        frames.append((n, [f"ngs{kind[:3]}_{c}" for c in num]))
    return frames


def team_pace() -> pl.DataFrame:
    rows = []
    for s in SEASONS:
        try:
            p = nfl.load_pbp([s])
        except Exception:
            continue
        p = p.filter((pl.col("season_type") == "REG") & ((pl.col("pass") == 1) | (pl.col("rush") == 1)) & pl.col("posteam").is_not_null())
        rows.append(
            p.group_by("posteam", "season", "week").agg(
                pl.len().alias("plays"), pl.col("qb_dropback").sum().alias("dropbacks"),
                pl.col("pass_oe").mean().alias("pass_oe"), pl.col("epa").mean().alias("team_epa"),
            ).rename({"posteam": "team"})
        )
    t = pl.concat(rows).sort("team", "season", "week")
    return t.with_columns(
        *[pl.col(c).ewm_mean(half_life=EWM_HL).shift(1).over("team").alias(f"pace_{c}") for c in ("plays", "dropbacks", "pass_oe", "team_epa")]
    ).select("team", "season", "week", *[f"pace_{c}" for c in ("plays", "dropbacks", "pass_oe", "team_epa")])


def participation_features() -> pl.DataFrame:
    """Each player's share of his team's pass plays and run plays he was on the field for,
    weighted over earlier games (a route-participation proxy and the passing-down split)."""
    frames = []
    for s in SEASONS:
        try:
            part = nfl.load_participation([s]).select(
                "nflverse_game_id", pl.col("play_id").cast(pl.Int64), "offense_players"
            )
            pbp = nfl.load_pbp([s]).filter(pl.col("season_type") == "REG").select(
                pl.col("game_id").alias("nflverse_game_id"), pl.col("play_id").cast(pl.Int64), "week", "posteam", "qb_dropback", "rush"
            )
        except Exception:
            continue
        plays = part.join(pbp, on=["nflverse_game_id", "play_id"], how="inner").filter(pl.col("posteam").is_not_null())
        plays = plays.with_columns(
            pl.col("qb_dropback").fill_null(0).cast(pl.Int64).alias("is_pass"), pl.col("rush").fill_null(0).cast(pl.Int64).alias("is_run")
        )
        team = plays.group_by("posteam", "week").agg(pl.col("is_pass").sum().alias("team_pass"), pl.col("is_run").sum().alias("team_run"))
        on = (
            plays.with_columns(pl.col("offense_players").str.split(";").alias("gsis_id"))
            .explode("gsis_id").filter(pl.col("gsis_id").is_not_null() & (pl.col("gsis_id") != ""))
            .group_by("gsis_id", "posteam", "week").agg(pl.col("is_pass").sum().alias("pass_on"), pl.col("is_run").sum().alias("run_on"))
            .join(team, on=["posteam", "week"])
            .with_columns(
                (pl.col("pass_on") / pl.col("team_pass")).alias("part_pass_share"),
                (pl.col("run_on") / pl.col("team_run")).alias("part_run_share"),
                pl.col("pass_on").cast(pl.Float64).alias("part_pass_snaps"),
                pl.lit(s).cast(pl.Int32).alias("season"),
            )
            .select("gsis_id", "season", pl.col("week").cast(pl.Int32), "part_pass_share", "part_run_share", "part_pass_snaps")
        )
        frames.append(on)
    return pl.concat(frames)


def depth_features() -> pl.DataFrame:
    """Depth chart rank at the position (1 is the starter) as of the game: the published week
    before 2025, the latest snapshot before the game day from 2025."""
    old = nfl.load_depth_charts(seasons=[s for s in SEASONS if s <= 2024]).filter(
        (pl.col("game_type") == "REG") & (pl.col("formation") == "Offense") & pl.col("position").is_in(["QB", "RB", "WR", "TE"])
    )
    old = old.with_columns(pl.col("depth_team").cast(pl.Float64, strict=False)).group_by("gsis_id", "season", "week").agg(
        pl.col("depth_team").min().alias("depth_rank")
    )
    new_snap = nfl.load_depth_charts(seasons=[s for s in SEASONS if s >= 2025]).filter(pl.col("pos_abb").is_in(["QB", "RB", "WR", "TE"]))
    new_snap = new_snap.with_columns(pl.col("dt").str.to_datetime(time_zone="UTC").dt.replace_time_zone(None).alias("dt_ts"))
    sched = nfl.load_schedules(seasons=[s for s in SEASONS if s >= 2025]).filter(pl.col("game_type") == "REG")
    games = pl.concat(
        [sched.select("season", "week", pl.col(t).alias("team"), pl.col("gameday").str.to_date().cast(pl.Datetime).alias("kick")) for t in ("home_team", "away_team")]
    ).sort("kick")
    snaps = new_snap.select("team", "dt_ts").unique().sort("dt_ts")
    picked = games.join_asof(snaps, left_on="kick", right_on="dt_ts", by="team", strategy="backward")
    new = picked.join(new_snap.select("team", "dt_ts", "gsis_id", pl.col("pos_rank").cast(pl.Float64).alias("depth_rank")), on=["team", "dt_ts"]).group_by(
        "gsis_id", "season", "week"
    ).agg(pl.col("depth_rank").min())
    return pl.concat([old.with_columns(pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32)), new.with_columns(pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32))])


def fit_predict(d: pl.DataFrame, feats: list[str]) -> pl.DataFrame:
    train = d.filter(pl.col("season") <= TRAIN_END)
    test = d.filter((pl.col("season") > TRAIN_END) & (pl.col("ours") > 3))
    x = train[feats].to_numpy().astype(float)
    # a column that is empty or constant in training carries nothing and breaks the binning
    feats = [c for c, col in zip(feats, x.T, strict=True) if len(np.unique(col[np.isfinite(col)])) > 1]
    m = HistGradientBoostingRegressor(
        loss="squared_error", max_iter=400, learning_rate=0.03, max_leaf_nodes=15,
        min_samples_leaf=80, l2_regularization=5.0, random_state=0,
    )
    m.fit(train[feats].to_numpy(), train["points"].to_numpy())
    return test.select(*KEY, "position", "points", "ours").with_columns(pl.Series("pred", m.predict(test[feats].to_numpy())))


def compare(name: str, base: pl.DataFrame, new: pl.DataFrame) -> dict:
    j = base.join(new.select(*KEY, pl.col("pred").alias("pred_new")), on=KEY)
    se_base = (j["points"] - j["pred"]) ** 2
    se_new = (j["points"] - j["pred_new"]) ** 2
    weekly = j.with_columns(se_base.alias("a"), se_new.alias("b")).group_by("season", "week").agg(pl.col("a").mean(), pl.col("b").mean())
    diff = (weekly["a"] - weekly["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))
    by_pos = {
        p: round(float(np.sqrt(se_base.filter(j["position"] == p).mean())) - float(np.sqrt(se_new.filter(j["position"] == p).mean())), 3)
        for p in ("QB", "RB", "WR", "TE")
    }
    return {
        "group": name, "rmse": round(float(np.sqrt(se_new.mean())), 4),
        "gain": round(float(np.sqrt(se_base.mean())) - float(np.sqrt(se_new.mean())), 4), "paired_t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}", **{f"gain_{p}": v for p, v in by_pos.items()},
    }


def main() -> None:
    d, feats = base_frame()
    base = fit_predict(d, feats)
    print(f"base model: n={base.height}, RMSE {float(np.sqrt(((base['points'] - base['pred']) ** 2).mean())):.4f}, "
          f"our baseline {float(np.sqrt(((base['points'] - base['ours']) ** 2).mean())):.4f}")
    results = []

    def attempt(name: str, build) -> None:
        try:
            frame, cols = build()
            results.append(compare(name, base, fit_predict(frame, feats + cols)))
        except Exception as err:  # one failing dataset should not hide the rest
            print(f"{name}: FAILED {type(err).__name__}: {str(err)[:140]}")

    r = roster_features()
    rf = ["age", "years_exp", "draft_pick", "roster_active", "weight"]
    attempt("roster", lambda: (d.join(r, on=KEY, how="left"), rf))

    w = weather_features()
    wf = ["temp", "wind", "div_game", "rest", "indoor", "moneyline"]
    attempt("weather+rest", lambda: (d.join(w, on=["season", "week", "team"], how="left"), wf))

    pace = team_pace()
    pf = [c for c in pace.columns if c.startswith("pace_")]
    attempt("team pace", lambda: (d.join(pace, on=["team", "season", "week"], how="left"), pf))

    adv, af = d, []
    for table, cols in advanced_tables():
        adv = lag_asof(adv, table.unique(KEY), "gsis_id", cols)
        af += [f"adv_{c}" for c in cols]
    attempt("advanced (PFR+NGS)", lambda: (adv, af))

    part = participation_features()
    pcols = ["part_pass_share", "part_run_share", "part_pass_snaps"]
    dpart = lag_asof(d, part.unique(KEY), "gsis_id", pcols)
    attempt("participation", lambda: (dpart, [f"adv_{c}" for c in pcols]))

    depth = depth_features().unique(KEY)
    attempt("depth chart", lambda: (d.join(depth, on=KEY, how="left"), ["depth_rank"]))

    everything = adv.join(r, on=KEY, how="left").join(w, on=["season", "week", "team"], how="left").join(pace, on=["team", "season", "week"], how="left")
    attempt("all four", lambda: (everything, rf + wf + pf + af))
    everything = lag_asof(everything, part.unique(KEY), "gsis_id", pcols).join(depth, on=KEY, how="left")
    attempt("all six", lambda: (everything, rf + wf + pf + af + [f"adv_{c}" for c in pcols] + ["depth_rank"]))
    with pl.Config(tbl_rows=20, tbl_cols=14, tbl_width_chars=170):
        print(pl.DataFrame(results))


if __name__ == "__main__":
    main()
