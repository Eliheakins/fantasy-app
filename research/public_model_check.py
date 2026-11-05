"""Can a public build drop the data it may not redistribute or train on, and what does it cost?

Licence findings (2026-11-05, docs/decisions.md): a public build may not use FantasyPros rankings
(`ecr_*`), Pro-Football-Reference snap counts and advanced stats, Next Gen Stats, or the depth
chart (ESPN-scraped from 2025, so the current season always needs it); the Vegas lines inside
nflverse schedules are unclear. Blocked inputs of the learned model, its stat-line chance q and
the availability classifier:
  learn       snap_hl2/4/8, snap_last (PFR snaps); depth_rank; ecr_* (6); adv_* (47 PFR and NGS
              columns); vacancy vac_out_snap, vac_q_snap (PFR snaps), eff_depth (depth) and the
              Questionable sit weights (who played, from PFR snaps)
  stat_line   h_snap, h_st, snap_last (PFR snaps), depth_rank; its training labels (snap-only
              played games are known only from PFR snaps)
  availability depth_rank, av_snap, weeks_since (PFR snaps)
Variants (the production code with its module constants patched in this process only):
  a_current   production as is
  b_removed   every blocked input dropped, nothing added; sit weights and q's labels from
              nflverse stat rows
  c_replaced  b plus `public_features.py`: involvement share for snap share, role rank for the
              depth rank (and so eff_depth), play-by-play efficiency stats for PFR/NGS
  d_no_lines  c without team_implied, total_line and spread (is_home stays: a game fact)
  b_plus_*    one replacement group added to b; c_no_adv, d_no_adv: c and d without the pbp
              efficiency stats (added after b_plus_adv showed no gain)
Evaluation (private, so it keeps the current definitions): played games are offensive snaps or a
stat row (PFR snaps decide the set), scored 2024 on with every model fit on earlier seasons
(`learn.walk_forward`); `learn.compare_to_baseline` and `hurdle_on_played` rows; RMSE and MAE of
q * E by position on played games; `backtest` RMSE, MAE and pinball by position one and five
games ahead; `ros_check` rest-of-season sums; availability Brier on the classifier's own rows
(depth-chart regulars, label any offensive snap); props blend on the free 2024 FanDuel archive
(`props_check.py`) and our own Odds API snapshots (one scored slate, 2026 week 7).

Run from the repo root (a worktree with its own copy of data/):
  OMP_NUM_THREADS=3 uv run python research/public_model_check.py <variant> [--ros] [--props]
  uv run python research/public_model_check.py --report | --availability | --own-props
(--availability rescores the availability model into the saved results; --own-props scores the
saved q * E of each variant against our own prop snapshots.)
Results go to research/scratch/public_model/<variant>.json; --report prints the tables.
"""

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.metrics import brier_score_loss

sys.path.insert(0, str(Path(__file__).parent))
import public_features as pf  # noqa: E402

from fantasy import stat_line_table, store  # noqa: E402
from fantasy.stages import availability, backtest, learn, stat_line, vacancy  # noqa: E402
from fantasy.stages.lags import lag_asof, latest_asof, train_seasons  # noqa: E402
from fantasy.stages.project import FIRST_PROJECTED_SEASON, GROUP, expected_frame, history_targets  # noqa: E402

OUT = Path(__file__).resolve().parent / "scratch" / "public_model"
KEYS = [*GROUP, "season", "week"]
SCORED_FROM = learn.FIRST_ACCEPTANCE_SEASON
# variant -> (replacement groups, schedule Vegas lines); a_current is production untouched
VARIANTS: dict[str, tuple[frozenset[str], bool] | None] = {
    "a_current": None,
    "b_removed": (frozenset(), True),
    "c_replaced": (frozenset({"inv", "role", "adv"}), True),
    "d_no_lines": (frozenset({"inv", "role", "adv"}), False),
    "b_plus_inv": (frozenset({"inv"}), True),  # one replacement group at a time on b
    "b_plus_role": (frozenset({"role"}), True),
    "b_plus_adv": (frozenset({"adv"}), True),
    # added after the runs above: the play-by-play efficiency group alone made b worse
    "c_no_adv": (frozenset({"inv", "role"}), True),
    "d_no_adv": (frozenset({"inv", "role"}), False),
}
SNAP_STATE = [f"snap_{s}" for s in ("hl2", "hl4", "hl8", "last")]
BLOCKED_EXTRA = {"depth_rank", "eff_depth", "vac_out_snap", "vac_q_snap", *learn.ECR_COLUMNS}
VEGAS = ["team_implied", "total_line", "spread"]
SNAP_COLUMNS = ["gsis_id", "season", "week", "team", "position", "offense_snaps", "offense_pct", "st_pct"]
pl.Config(tbl_rows=60, tbl_cols=14, tbl_width_chars=200, float_precision=4)


# ---- inputs ---------------------------------------------------------------------------------


def raw() -> dict[str, pl.DataFrame]:
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    points = store.read_table("player_points")
    return {
        "leagues": leagues,
        "opp": opp,
        "points": points,
        "snaps": store.read_table("nfl_snaps", "raw"),
        "stats": store.read_table("nfl_player_stats", "raw"),
        "team_stats": store.read_table("nfl_team_stats", "raw"),
        "lines": store.read_table("team_games"),
        "exp": expected_frame(opp, points, leagues),
    }


def public_tables(r: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """public_features tables plus a snaps-shaped frame of involvement (offense_pct = share)."""
    tabs = pf.build(sorted(r["lines"]["season"].unique().to_list()), r["stats"], r["lines"])
    inv = tabs["involvement"].with_columns(
        (pl.col("inv") > 0).cast(pl.Float64).alias("offense_snaps"),
        pl.col("inv").alias("offense_pct"),
        pl.lit(None, pl.Float64).alias("st_pct"),
    )
    return {**tabs, "snaps_like": inv.select(SNAP_COLUMNS)}


def empty_snaps() -> pl.DataFrame:
    return pl.DataFrame(
        schema={c: pl.String if c in ("gsis_id", "team", "position") else pl.Float64 for c in SNAP_COLUMNS}
    ).with_columns(pl.col("season", "week").cast(pl.Int64))


def stat_played(stats: pl.DataFrame) -> pl.DataFrame:
    """A snaps-shaped frame marking every regular-season nflverse stat row as played: the public
    stand-in for "had offensive snaps" where a weight needs it (vacancy's sit weights)."""
    return stats.filter(pl.col("season_type") == "REG").select(
        pl.col("player_id").alias("gsis_id"), "season", "week", pl.lit(1.0).alias("offense_snaps")
    )


# ---- patching -------------------------------------------------------------------------------


@contextmanager
def patched(module: Any, **values: Any) -> Iterator[None]:
    old = {k: getattr(module, k) for k in values}
    for k, v in values.items():
        setattr(module, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(module, k, v)


def groups(variant: str) -> frozenset[str]:
    spec = VARIANTS[variant]
    return frozenset() if spec is None else spec[0]


def snaps_for(variant: str, pub: dict[str, pl.DataFrame]) -> pl.DataFrame:
    return pub["snaps_like"] if "inv" in groups(variant) else empty_snaps()


def depth_for(variant: str, pub: dict[str, pl.DataFrame]) -> pl.DataFrame:
    return pub["role"] if "role" in groups(variant) else pub["role"].clear()


def extras_for(variant: str, r: dict[str, pl.DataFrame], pub: dict[str, pl.DataFrame]) -> learn.Extras:
    base = learn.load_extras()
    if VARIANTS[variant] is None:
        return base
    usage = vacancy.usage_table(r["stats"], r["team_stats"], snaps_for(variant, pub))
    weights = vacancy.sit_weights(base.report, stat_played(r["stats"]), learn.FIRST_ACCEPTANCE_SEASON - 1)
    advanced = (
        pub["advanced"]
        if "adv" in groups(variant)
        else pl.DataFrame(schema={"gsis_id": pl.String, "season": pl.Int64, "week": pl.Int64})
    )
    return replace(
        base, depth=depth_for(variant, pub), advanced=advanced, usage=usage, sit_weights=weights
    )


@contextmanager
def variant_patches(variant: str, r: dict[str, pl.DataFrame], pub: dict[str, pl.DataFrame]) -> Iterator[learn.Extras]:
    """learn's feature lists, games frame and extras for the variant, and stat_line's features."""
    extras = extras_for(variant, r, pub)
    spec = VARIANTS[variant]
    if spec is None:
        with patched(learn, load_extras=lambda: extras):
            yield extras
        return
    group, with_lines = spec
    adv = list(pf.ADV_COLUMNS) if "adv" in group else []
    extra = [c for c in learn.EXTRA_FEATURES if c not in BLOCKED_EXTRA and not c.startswith("adv_")]
    state = [c for c in learn.STATE_FEATURES if "inv" in group or c not in SNAP_STATE]
    sl_features = [c for c in stat_line.FEATURES if c not in ("h_snap", "h_st", "snap_last", "depth_rank")]
    if "inv" in group:
        extra += ["vac_out_snap", "vac_q_snap"]
        sl_features += ["h_snap", "snap_last"]
    if "role" in group:
        extra += ["depth_rank", "eff_depth"]
        sl_features += ["depth_rank"]
    extra += [f"adv_{c}" for c in adv]
    snaps_for_games = snaps_for(variant, pub)
    lines = learn.LINE_FEATURES if with_lines else ["is_home"]
    original_games = learn.games_frame

    def games_frame(exp: pl.DataFrame, opp: pl.DataFrame, _snaps: pl.DataFrame, stats: pl.DataFrame) -> pl.DataFrame:
        return original_games(exp, opp, snaps_for_games, stats)

    with (
        patched(
            learn,
            load_extras=lambda: extras,
            games_frame=games_frame,
            STATE_FEATURES=state,
            EXTRA_FEATURES=extra,
            ADVANCED_COLUMNS=adv,
            LINE_FEATURES=lines,
        ),
        patched(stat_line, FEATURES=sl_features),
    ):
        yield extras


# ---- the stat-line chance q -----------------------------------------------------------------


def chance(variant: str, r: dict[str, pl.DataFrame], pub: dict[str, pl.DataFrame], eval_played: pl.DataFrame) -> pl.DataFrame:
    """KEY, q for every evaluation played game, walk-forward. The public variants learn from the
    games they could see (stat rows only) and their own features; `a_current` is
    `stat_line.history_chance` exactly."""
    if VARIANTS[variant] is None:
        train_played, snaps, depth = eval_played, r["snaps"], learn.load_extras().depth
    else:
        train_played = stat_line.played_rows(r["points"], r["exp"], empty_snaps(), r["opp"])
        snaps, depth = snaps_for(variant, pub), depth_for(variant, pub)
    history = stat_line.history_table(train_played, stat_line.usage_frame(r["opp"], snaps, r["stats"]))
    train = stat_line.features(train_played, history, depth).filter(pl.col("season") >= FIRST_PROJECTED_SEASON)
    test = stat_line.features(eval_played, history, depth).filter(pl.col("season") >= FIRST_PROJECTED_SEASON)
    seasons = sorted(test["season"].unique().to_list())
    parts = []
    for season in seasons:
        fit = train.filter(pl.col("season").is_in(train_seasons(season, seasons)))
        rows = test.filter(pl.col("season") == season)
        parts.append(rows.select(learn.KEY).with_columns(pl.Series("q", stat_line.fit_predict(fit, rows))))
    return pl.concat(parts).unique(learn.KEY, keep="first")


# ---- projections and scores -----------------------------------------------------------------


def past_projections(r: dict[str, pl.DataFrame], extras: learn.Extras, eval_played: pl.DataFrame) -> pl.DataFrame:
    """E for every past game, as `learn.league_projections` makes it (stat-less played games
    projected, never trained on)."""
    games_all = learn.games_frame(r["exp"], r["opp"], r["snaps"], r["stats"])
    parts = []
    for lid in r["leagues"]["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        state = learn.state_frame(games)
        targets = history_targets(r["exp"].filter(pl.col("league_id") == lid))
        history = learn.build_features(targets, state, r["lines"], extras).join(
            games.select(*KEYS, "points"), on=KEYS
        )
        extra = learn.build_features(stat_line.statless_targets(eval_played, lid), state, r["lines"], extras)
        parts.append(
            learn.walk_forward(history, extra=extra).select(
                *KEYS, "position", "team", "as_of_season", "as_of_week", "has_history", "projection"
            )
        )
    return pl.concat(parts).with_columns(is_future=pl.lit(False))


@contextmanager
def as_stored(learned: pl.DataFrame, q: pl.DataFrame) -> Iterator[None]:
    """Make store reads of proj_learned and the stat_line table return this variant's frames."""
    original = store.read_table

    def read(name: str, area: str = "derived", data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
        return learned if name == "proj_learned" else original(name, area, data_dir)

    with patched(store, read_table=read, write_table=lambda *a, **k: None), patched(
        stat_line_table, stored=lambda *a, **k: q
    ):
        yield


def played_scores(learned: pl.DataFrame) -> pl.DataFrame:
    """RMSE and MAE of q * E on every played game from SCORED_FROM, by league and position."""
    rows = (
        learned.filter(pl.col("season") >= SCORED_FROM)
        .join(store.read_table("player_points").select(*KEYS, "points"), on=KEYS, how="left")
        .with_columns(pl.col("points").fill_null(0.0), (pl.col("projection") - pl.col("points").fill_null(0.0)).alias("err"))
    )
    by = [
        rows.group_by("league_id", "position"),
        rows.with_columns(pl.lit("ALL").alias("position")).group_by("league_id", "position"),
    ]
    return pl.concat(
        [g.agg(pl.len().alias("n"), (pl.col("err") ** 2).mean().sqrt().alias("rmse"), pl.col("err").abs().mean().alias("mae")) for g in by]
    ).sort("league_id", "position")


def weekly_se(learned: pl.DataFrame) -> pl.DataFrame:
    """Per league and week, the mean squared error of q * E on played games (for paired t)."""
    return (
        learned.filter(pl.col("season") >= SCORED_FROM)
        .join(store.read_table("player_points").select(*KEYS, "points"), on=KEYS, how="left")
        .with_columns(((pl.col("projection") - pl.col("points").fill_null(0.0)) ** 2).alias("se"))
        .group_by("league_id", "season", "week")
        .agg(pl.col("se").mean())
    )


# ---- availability ---------------------------------------------------------------------------


def availability_brier(variant: str, r: dict[str, pl.DataFrame], pub: dict[str, pl.DataFrame]) -> dict[str, float]:
    """Brier of the chance-of-playing classifier on its own rows (depth-chart regulars, label any
    offensive snap), each season from 2024 scored by a model fit on the seasons before it (played
    weeks only); all rows and rows on the injury report, pooled and by season."""
    rows = availability.build_rows()
    played_weeks = r["lines"].filter(pl.col("points_for").is_not_null()).select("season", "week").unique()
    rows = rows.join(played_weeks, on=["season", "week"], how="semi")
    numeric = list(availability.NUMERIC)
    if VARIANTS[variant] is not None:
        seen = stat_played(r["stats"]).with_columns((pl.col("season") * 18 + pl.col("week")).alias("when_pub"))
        rows = latest_asof(rows, seen.select(*learn.KEY, "when_pub"), "gsis_id", ["when_pub"], shift=1).with_columns(
            (pl.col("season") * 18 + pl.col("week") - pl.col("when_pub") - 1).clip(0, 40).alias("ws_pub")
        )
        numeric = ["ws_pub", "age"]
        if "inv" in groups(variant):
            rows = lag_asof(rows, pub["involvement"], "gsis_id", ["inv"], "av")
            numeric += ["av_inv"]
        if "role" in groups(variant):
            rows = rows.join(pub["role"].rename({"depth_rank": "role_rank"}), on=learn.KEY, how="left")
            numeric += ["role_rank"]
    test = rows.filter(pl.col("season") >= SCORED_FROM)
    preds = []
    with patched(availability, NUMERIC=numeric):
        for season in sorted(test["season"].unique().to_list()):  # walk-forward, like learn
            train = rows.filter(pl.col("season") < season)
            part = test.filter(pl.col("season") == season)
            preds.append(availability.fit_predict(availability.design(train), train["played"].to_numpy(), availability.design(part)))
    test = test.sort("season", maintain_order=True)
    pred, y = np.concatenate(preds), test["played"].to_numpy()
    listed = (test["status"] != "none").to_numpy()
    out: dict[str, Any] = {
        "n": int(len(y)),
        "brier": float(brier_score_loss(y, pred)),
        "n_listed": int(listed.sum()),
        "brier_listed": float(brier_score_loss(y[listed], pred[listed])),
    }
    seasons = test["season"].to_numpy()
    for season in np.unique(seasons):
        k = seasons == season
        out[f"brier_{season}"] = float(brier_score_loss(y[k], pred[k]))
        out[f"brier_listed_{season}"] = float(brier_score_loss(y[k & listed], pred[k & listed]))
    return out


# ---- rest of season, backtest, props ---------------------------------------------------------


def horizon_forecasts(horizons: range) -> dict[int, pl.DataFrame]:
    return {k: learn.history_forecasts(k) for k in horizons}


def ros(forecasts: dict[int, pl.DataFrame]) -> list[dict[str, Any]]:
    import ros_check

    with patched(ros_check, history_forecasts=lambda k: forecasts[k]):
        rows = ros_check.forecasts()
    out = []
    for lid in sorted(rows["league_id"].unique().to_list()):
        sums = ros_check.ros_sums(rows, lid)
        s = ros_check.summarize(sums).filter(pl.col("forecast") != "mix")
        out += [{"league_id": lid, **d} for d in s.to_dicts()]
    return out


def props_2024() -> str:
    """props_check.py's report on the free 2024 archive for the patched proj_learned (stdout)."""
    import io
    from contextlib import redirect_stdout

    import props_check

    buffer = io.StringIO()
    with redirect_stdout(buffer), patched(sys, argv=[sys.argv[0]]):  # it reads argv[1] as a path
        props_check.main()
    return buffer.getvalue()


OWN_MAX_AGE_HOURS = 72  # the archive's one scored slate (2026 week 7) was taken 44 to 56 hours out


def props_own(learned: pl.DataFrame, r: dict[str, pl.DataFrame]) -> list[dict[str, Any]]:
    """Our own Odds API snapshots (data/archive/odds): every scored week with a snapshot taken
    before kickoff (within OWN_MAX_AGE_HOURS, not production's 36); ours (q * E) against the equal
    blend with prop-implied points, RB and WR covered rows, as `prop_points` builds them."""
    from fantasy.stages import prop_points

    with patched(prop_points, MAX_LINE_AGE_HOURS=OWN_MAX_AGE_HOURS):
        return _props_own(learned, r, prop_points)


def _props_own(learned: pl.DataFrame, r: dict[str, pl.DataFrame], prop_points: Any) -> list[dict[str, Any]]:
    lines_all = prop_points.read_snapshots()
    people = prop_points.current_people(store.DATA_DIR)
    sched = store.read_table("nfl_schedules", "raw")
    out = []
    played_weeks = r["lines"].filter(pl.col("points_for").is_not_null() & (pl.col("season") == 2026))
    for week in sorted(played_weeks["week"].unique().to_list()):
        week_sched = sched.filter((pl.col("season") == 2026) & (pl.col("week") == week))
        lines = prop_points.week_lines(lines_all, week_sched)
        if lines.is_empty():
            continue
        props = prop_points.map_players(lines, people)
        for lg in r["leagues"].iter_rows(named=True):
            scoring = json.loads(lg["scoring_settings"])
            pts = r["points"].filter(pl.col("league_id") == lg["league_id"])
            lags = prop_points.lagged_means(pts, r["stats"], scoring, 2026, week)
            implied = prop_points.implied_points(props, lags, scoring, ["RB", "WR"])
            rows = (
                learned.filter((pl.col("league_id") == lg["league_id"]) & (pl.col("season") == 2026) & (pl.col("week") == week))
                .join(implied.rename({"projection": "props"}), on="gsis_id")
                .join(pts.select(*KEYS, "points"), on=KEYS, how="left")
                .with_columns(pl.col("points").fill_null(0.0), ((pl.col("projection") + pl.col("props")) / 2).alias("blend"))
            )
            if rows.is_empty():
                continue
            out.append(
                {
                    "league_id": lg["league_id"],
                    "week": week,
                    "n": rows.height,
                    "rmse_learned": float(np.sqrt(((rows["projection"] - rows["points"]) ** 2).mean())),
                    "rmse_blend": float(np.sqrt(((rows["blend"] - rows["points"]) ** 2).mean())),
                }
            )
    return out


# ---- run ------------------------------------------------------------------------------------


def run(variant: str, do_ros: bool, do_props: bool) -> None:
    r = raw()
    pub = public_tables(r) if VARIANTS[variant] is not None else {}
    eval_played = stat_line.played_rows(r["points"], r["exp"], r["snaps"], r["opp"])
    result: dict[str, Any] = {"variant": variant}
    with variant_patches(variant, r, pub) as extras:
        print(f"{variant}: {len(learn.STATE_FEATURES)} state, {len(learn.EXTRA_FEATURES)} extra, lines {learn.LINE_FEATURES}")
        q = chance(variant, r, pub, eval_played)
        e = past_projections(r, extras, eval_played)
        learned = learn.with_context(stat_line_table.scale(e, q, learn.KEY), store.read_table("proj_baseline"), None)
        OUT.mkdir(parents=True, exist_ok=True)
        learned.select(*KEYS, "position", "projection").write_parquet(OUT / f"{variant}_learned.parquet")
        weekly_se(learned).write_parquet(OUT / f"{variant}_weekly.parquet")
        with as_stored(learned, q):
            result["compare"] = learn.compare_to_baseline().drop("passes").to_dicts()
            result["hurdle"] = learn.hurdle_on_played().to_dicts()
            result["played"] = played_scores(learned).to_dicts()
            result["availability"] = availability_brier(variant, r, pub)
            print(json.dumps(result, indent=1, default=str))
            if do_props:
                result["props_2024"] = props_2024()
                result["props_own"] = props_own(learned, r)
                print(result["props_2024"], result["props_own"])
            if do_ros:
                forecasts = horizon_forecasts(range(1, 7))
                with patched(backtest, history_forecasts=lambda k: forecasts[k]):
                    result["backtest"] = backtest.run().filter(pl.col("tier") == backtest.ALL_TIERS).drop("tier", "coverage80").to_dicts()
                result["ros"] = ros(forecasts)
    (OUT / f"{variant}.json").write_text(json.dumps(result, indent=1, default=str))
    print(f"wrote {OUT / f'{variant}.json'}")


# ---- report ---------------------------------------------------------------------------------


def paired_t(variant: str) -> pl.DataFrame:
    """Per league: paired per-week t of a_current's weekly MSE minus the variant's (negative:
    the variant is worse), and weeks the variant won."""
    a = pl.read_parquet(OUT / "a_current_weekly.parquet")
    v = pl.read_parquet(OUT / f"{variant}_weekly.parquet")
    rows = []
    for (lid,), g in a.join(v, on=["league_id", "season", "week"], suffix="_v").group_by("league_id"):
        d = (g["se"] - g["se_v"]).to_numpy()
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.any() else 0.0
        rows.append({"league_id": lid, "t_vs_a": round(t, 2), "weeks_won": f"{int((d > 0).sum())}/{len(d)}"})
    return pl.DataFrame(rows)


def report() -> None:
    results = {v: json.loads((OUT / f"{v}.json").read_text()) for v in VARIANTS if (OUT / f"{v}.json").exists()}
    base = results["a_current"]
    names = {r["league_id"]: n for r, n in zip(sorted(base["hurdle"], key=lambda r: r["league_id"]), ("YinzBurgh", "Colgate"), strict=True)}

    def frame(key: str, **extra: Any) -> pl.DataFrame:
        return pl.concat(
            [pl.DataFrame(res[key]).with_columns(pl.lit(v).alias("variant")) for v, res in results.items() if key in res],
            how="diagonal_relaxed",
        ).with_columns(pl.col("league_id").replace_strict(names).alias("league"))

    print("Played games (q * E, 2024 on): RMSE, change against a_current, paired per-week t")
    played = frame("played")
    ref = played.filter(pl.col("variant") == "a_current").select("league", "position", pl.col("rmse").alias("rmse_a"), pl.col("mae").alias("mae_a"))
    played = played.join(ref, on=["league", "position"]).with_columns(
        (100 * (pl.col("rmse") / pl.col("rmse_a") - 1)).round(2).alias("rmse_pct"),
        (100 * (pl.col("mae") / pl.col("mae_a") - 1)).round(2).alias("mae_pct"),
    )
    ts = pl.concat([paired_t(v).with_columns(pl.lit(v).alias("variant")) for v in results if v != "a_current"])
    overall = played.filter(pl.col("position") == "ALL").join(ts.with_columns(pl.col("league_id").replace_strict(names).alias("league")).drop("league_id"), on=["variant", "league"], how="left")
    print(overall.select("variant", "league", "n", "rmse", "rmse_pct", "mae", "mae_pct", "t_vs_a", "weeks_won").sort("league", "variant"))
    print(played.filter(pl.col("position") != "ALL").pivot("position", index=["variant", "league"], values="rmse_pct").sort("league", "variant"))
    print("compare_to_baseline rows (E, the learned model against the size-calibrated baseline)")
    print(frame("compare").select("variant", "league", "n", "rmse_baseline", "rmse_learned", "gain_pct", "paired_t", "weeks_better").sort("league", "variant"))
    print("hurdle_on_played (q * E against E, played games)")
    print(frame("hurdle").select("variant", "league", "rmse_e", "rmse_q_e", "gain_pct", "paired_t").sort("league", "variant"))
    if any("backtest" in r for r in results.values()):
        bt = frame("backtest").filter(pl.col("forecaster") == "learned")
        bref = bt.filter(pl.col("variant") == "a_current").select("league", "position", "horizon", pl.col("pinball").alias("pin_a"), pl.col("rmse").alias("rmse_a"))
        bt = bt.join(bref, on=["league", "position", "horizon"]).with_columns(
            (100 * (pl.col("pinball") / pl.col("pin_a") - 1)).round(2).alias("pinball_pct"),
            (100 * (pl.col("rmse") / pl.col("rmse_a") - 1)).round(2).alias("rmse_pct"),
        )
        print("backtest (E on stat-line games, 2024 on), learned forecaster: pinball and RMSE change against a_current")
        for h in (1, 5):
            print(f"horizon {h}")
            print(bt.filter(pl.col("horizon") == h).pivot("position", index=["variant", "league"], values=["pinball_pct", "rmse_pct"]).sort("league", "variant"))
        print(bt.filter((pl.col("variant") == "a_current")).select("league", "position", "horizon", "rmse", "mae", "pinball").sort("horizon", "league", "position"))
    if any("ros" in r for r in results.values()):
        print("rest of season (ros_check: 6-game sums, 2024 to 2025 origins)")
        print(frame("ros").select("variant", "league", "forecast", "players", "rmse_of_sum", "mean_error", "spearman").sort("league", "forecast", "variant"))
    print("availability classifier, Brier (2024 on, played weeks)")
    print(pl.DataFrame([{"variant": v, **r["availability"]} for v, r in results.items()]))
    for v, r in results.items():
        if "props_own" in r:
            print(f"{v}: own Odds API snapshots {r['props_own']}")
            print(f"{v}: props_check 2024 (last lines)\n" + "\n".join(line for line in r["props_2024"].splitlines() if "pass" in line or "RMSE" in line))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--report" in sys.argv:
        report()
        return
    if "--availability" in sys.argv:  # rescore availability alone into each saved result
        r = raw()
        pub = public_tables(r)
        for v in VARIANTS:
            path = OUT / f"{v}.json"
            if path.exists():
                res = json.loads(path.read_text())
                res["availability"] = availability_brier(v, r, pub)
                path.write_text(json.dumps(res, indent=1, default=str))
                print(v, res["availability"])
        return
    if "--own-props" in sys.argv:  # from the saved q * E of each variant run
        r = raw()
        for v in VARIANTS:
            path = OUT / f"{v}_learned.parquet"
            if path.exists():
                print(v, props_own(pl.read_parquet(path), r))
        return
    for variant in args or VARIANTS:
        if variant not in VARIANTS:
            raise SystemExit(f"unknown variant {variant}; one of {VARIANTS}")
        run(variant, "--ros" in sys.argv, "--props" in sys.argv)


if __name__ == "__main__":
    main()
