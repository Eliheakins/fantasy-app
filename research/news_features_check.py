"""Do injury-report ("news") features help the learned model held out?

Two feature sets, each added alone to the production model (`learn.build_features`, `learn.design`,
`learn.fit_predict`, `learn.train_seasons`), then together:

  vac   teammate vacancy for the target game, from the FINAL nflverse injury report of that game
        and each listed teammate's usage strictly before it (`lags.lag_asof`, half-life 4):
        share of team targets and carries held by skill teammates listed Out or Doubtful, the
        same-position snap share they held, the same three for Questionable teammates weighted by
        the chance a Questionable player sits given his final practice (fit on 2018 to 2023
        only), and an effective depth rank (the game's chart rank minus same-position teammates
        listed Out or Doubtful ranked above him).
  own   the player's own final status (none, Questionable, Doubtful, Out), final practice (Full,
        Limited, DNP; missing when not on the report) and body-part group (soft tissue, joint,
        head, other), in the learned model and in the stat-line q model.

Production is q * E plus two layers. Each arm is scored with the layers as production applies
them, estimated per held-out season on earlier seasons (2021 on) of that arm's own walk-forward
projections, per league:
  outlook  return ratios and teammate vacancy slopes (`stages/outlook.py`, applied the way
           research/layers_check.py does; `vacoff` drops the vacancy slopes)
  perf     the injury table's play-through ratio for a listed player (`stages/injuries.py`)
Arms: base (current model, outlook + perf), vac_b (vac features, outlook returns only + perf),
vac_c (vac features, outlook + perf), own_b (own features, outlook, no perf), own_c (own features,
outlook + perf), each candidate's placebo (its columns shuffled within position-week, scored with
the candidate's layers), and raw (no layers) versions.

Scored on 2024, 2025 and 2026 weeks 1 to 6, every played game (offensive snaps or a player_points
row; a played game without one scores 0): played RMSE of the layered q * E; protocol rows
(`learn.compare_to_baseline`'s: has history, size-calibrated baseline above 3) on raw E. Paired
weekly t, by season and position, and on games where a skill teammate was listed Out or Doubtful.

Ship rule (fixed before the run): played RMSE lower than base in both leagues, pooled |t| >= 2 in
at least one, no league-season t <= -1, lower than its placebo in both leagues, and protocol-row
RMSE (raw E against raw base E) not worse by more than 0.05%.

Serve-time check: the final nflverse report of a week appears Friday; before that the only status
is Sleeper's `injury_status`. Compared on 2026 week 7, the one week with both in this data copy.

Since the review (2026-10-26) the vac columns are the shipped ones (`stages/vacancy.py`, built by
`learn.build_features`: a teammate vacates only the usage he had with the listed team), the base
design is `learn.design(..., vacancy=False)`, the serve stand-in is Sleeper's Out list only, and
`standin_check` scores 2026 week 7's played games with the stand-in in place of the final report.
`--vac-only` runs the base and vac arms only.

Each arm's predictions go to the scratchpad preds folder for research/regret.py.

Run from the repo root (data/ must hold the tables):
    OMP_NUM_THREADS=3 uv run python research/news_features_check.py [--fresh]
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import polars as pl
import polars.selectors as cs

sys.path.insert(0, str(Path(__file__).parent))
import layers_check  # noqa: E402
import pbp_features_check as pbp  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.sim.injuries import InjuryModel  # noqa: E402
from fantasy.stages import injuries as inj_stage  # noqa: E402
from fantasy.stages import learn, stat_line, vacancy  # noqa: E402
from fantasy.stages import outlook as out  # noqa: E402
from fantasy.stages.lags import lag_asof, train_seasons  # noqa: E402
from fantasy.stages.project import GROUP, expected_frame, history_targets  # noqa: E402
from fantasy.store import SKILL  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch" / "news"
PREDS = Path(
    "/private/tmp/claude-501/-Users-eliheakins-personal-fantasy-app/"
    "230639a7-242c-4003-bae2-a92998c4f96c/scratchpad/preds"
)
KEY = ["gsis_id", "season", "week"]
KEYS = [*GROUP, "season", "week"]
SCORED = (2024, 2025, 2026)
LAST_2026_WEEK = 6
FIRST_CLEAN = 2021  # walk-forward projections before this saw later seasons
WEIGHT_SEASONS = (2018, 2023)  # Questionable sit rates are fit on these only
PLACEBO_SEED = 7
MAX_PROTOCOL_LOSS = 0.05
MIN_T = 2.0
OUT_STATUSES = ("Out", "Doubtful")
STATUS_CODE = {"Questionable": 1.0, "Doubtful": 2.0, "Out": 3.0}
PRACTICE_CODE = {"Full": 0.0, "Limited": 1.0, "DNP": 2.0}
BODY_GROUPS = {
    "soft": ("Hamstring", "Groin", "Calf", "Quadricep"),
    "joint": ("Ankle", "Knee", "Foot", "Hip", "Shoulder", "Back"),
    "head": ("Concussion",),
}
VAC_COLS = ["vac_out_tgt", "vac_out_car", "vac_out_snap", "vac_q_tgt", "vac_q_car", "vac_q_snap",
            "eff_depth"]  # fmt: skip
OWN_COLS = ["own_status", "own_practice", "own_soft", "own_joint", "own_head", "own_other"]
SLEEPER_TO_REPORT = {"Out": "Out", "Doubtful": "Doubtful", "Questionable": "Questionable"}
pl.Config(tbl_rows=120, tbl_cols=24, tbl_width_chars=240, float_precision=4)


# ---- report tables ----------------------------------------------------------------------------


def report_table(injuries: pl.DataFrame) -> pl.DataFrame:
    """KEY, team, position, status (Out, Doubtful, Questionable or None), practice (Full,
    Limited, DNP or None), body (raw) from the final regular-season report of each game week."""
    return (
        injuries.filter(pl.col("game_type") == "REG")
        .unique(KEY, keep="first", maintain_order=True)
        .select(
            *KEY,
            "team",
            "position",
            pl.when(pl.col("report_status").is_in(list(STATUS_CODE)))
            .then(pl.col("report_status"))
            .alias("status"),
            pl.col("practice_status").replace_strict(inj_stage.PRACTICE, default=None).alias("practice"),
            pl.coalesce("report_primary_injury", "practice_primary_injury").alias("body"),
        )
    )


def sleeper_report(sleeper: pl.DataFrame, teams: pl.DataFrame, season: int, week: int) -> pl.DataFrame:
    """The serve-time stand-in: Sleeper injury_status mapped to the report's categories (IR, PUP,
    NA and the rest are not game statuses), practice and body unknown. Team and position from
    each player's latest nflverse snap row (teams: gsis_id, team, position)."""
    return (
        sleeper.filter(pl.col("gsis_id").is_not_null())
        .select(
            "gsis_id",
            pl.col("injury_status").replace_strict(SLEEPER_TO_REPORT, default=None).alias("status"),
        )
        .filter(pl.col("status").is_not_null())
        .join(teams, on="gsis_id", how="inner")
        .with_columns(
            pl.lit(season).alias("season"),
            pl.lit(week).alias("week"),
            pl.lit(None, pl.String).alias("practice"),
            pl.lit(None, pl.String).alias("body"),
        )
        .select(*KEY, "team", "position", "status", "practice", "body")
    )


def sit_weights(report: pl.DataFrame, snaps: pl.DataFrame) -> dict[str | None, float]:
    """Practice -> share of Questionable skill players who did not play (no offensive snaps),
    on WEIGHT_SEASONS only; None (practice unknown) gets the pooled share."""
    played = snaps.filter(pl.col("offense_snaps") > 0).select(KEY).unique().with_columns(p=pl.lit(1.0))
    q = (
        report.filter(
            (pl.col("status") == "Questionable")
            & pl.col("position").is_in(SKILL)
            & pl.col("season").is_between(*WEIGHT_SEASONS)
        )
        .join(played, on=KEY, how="left")
        .with_columns(pl.col("p").fill_null(0.0))
    )
    weights: dict[str | None, float] = {
        r["practice"]: 1.0 - r["p"] for r in q.group_by("practice").agg(pl.col("p").mean()).iter_rows(named=True)
    }
    weights[None] = 1.0 - float(q["p"].mean())  # type: ignore[arg-type]
    print("Questionable sit weights (2018-2023):", {k: round(v, 3) for k, v in weights.items()})
    return weights


def usage_table(stats: pl.DataFrame, team_stats: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """KEY, tgt (target share), car (carry share), snap (offense pct) per player-game."""
    shares = out.usage_table(stats, team_stats).select(
        *KEY, pl.col("target_share").alias("tgt"), pl.col("carry_share").alias("car")
    ).unique(KEY, keep="first")
    snap = (
        snaps.filter(pl.col("gsis_id").is_not_null())
        .select(*KEY, pl.col("offense_pct").cast(pl.Float64).alias("snap"))
        .unique(KEY, keep="first")
    )
    return shares.join(snap, on=KEY, how="full", coalesce=True)


# ---- features ---------------------------------------------------------------------------------


def vacancy_features(
    targets: pl.DataFrame,
    report: pl.DataFrame,
    usage: pl.DataFrame,
    weights: dict[str | None, float],
    depth: pl.DataFrame,
) -> pl.DataFrame:
    """targets (KEY, team, position, depth_rank) with VAC_COLS. Each listed teammate's usage is
    his weighted average over games strictly before the target game; the report is the game's."""
    listed = report.filter(pl.col("status").is_not_null() & pl.col("position").is_in(SKILL))
    wmap = {k: v for k, v in weights.items() if k is not None}
    listed = listed.with_columns(
        pl.when(pl.col("status").is_in(OUT_STATUSES)).then(pl.lit("out")).otherwise(pl.lit("q")).alias("kind"),
        pl.when(pl.col("status").is_in(OUT_STATUSES))
        .then(1.0)
        .otherwise(
            pl.col("practice")
            .replace_strict(wmap, default=weights[None], return_dtype=pl.Float64)
            .fill_null(weights[None])
        )
        .alias("w"),
    )
    lagged = lag_asof(listed, usage, "gsis_id", ["tgt", "car", "snap"], "u").with_columns(
        [(pl.col(f"u_{c}").fill_null(0.0) * pl.col("w")).alias(c) for c in ("tgt", "car", "snap")]
    )
    team_keys = ["team", "season", "week"]
    out_frame = targets
    for kind in ("out", "q"):
        part = lagged.filter(pl.col("kind") == kind)
        team = part.group_by(team_keys).agg(pl.col("tgt", "car").sum().name.prefix("_t_"))
        pos = part.group_by(*team_keys, "position").agg(pl.col("snap").sum().alias("_t_snap"))
        own = part.select(*KEY, pl.col("tgt", "car", "snap").name.prefix("_o_"))
        out_frame = (
            out_frame.join(team, on=team_keys, how="left")
            .join(pos, on=[*team_keys, "position"], how="left")
            .join(own, on=KEY, how="left")
            .with_columns(
                [
                    (pl.col(f"_t_{c}").fill_null(0.0) - pl.col(f"_o_{c}").fill_null(0.0))
                    .clip(lower_bound=0.0)
                    .alias(f"vac_{kind}_{c}")
                    for c in ("tgt", "car", "snap")
                ]
            )
            .drop(cs.starts_with("_t_", "_o_"))
        )
    chart = depth.select(*KEY, pl.col("depth_rank").alias("_mate_rank")).unique(KEY, keep="first")
    mates = (
        listed.filter(pl.col("kind") == "out")
        .join(chart, on=KEY, how="inner")
        .select(pl.col("gsis_id").alias("_mate"), *team_keys, "position", "_mate_rank")
    )
    above = (
        targets.select(*KEY, "team", "position", "depth_rank")
        .join(mates, on=[*team_keys, "position"], how="inner")
        .filter((pl.col("_mate") != pl.col("gsis_id")) & (pl.col("_mate_rank") < pl.col("depth_rank")))
        .group_by(KEY)
        .agg(pl.len().cast(pl.Float64).alias("_above"))
    )
    return (
        out_frame.join(above, on=KEY, how="left")
        .with_columns((pl.col("depth_rank") - pl.col("_above").fill_null(0.0)).alias("eff_depth"))
        .drop("_above")
    )


def own_features(targets: pl.DataFrame, report: pl.DataFrame) -> pl.DataFrame:
    """targets with OWN_COLS from the player's own final report row for the game."""
    groups = [
        pl.col("body").is_in(list(bodies)).cast(pl.Float64).alias(f"own_{name}")
        for name, bodies in BODY_GROUPS.items()
    ]
    rows = report.select(
        *KEY,
        pl.col("status").replace_strict(STATUS_CODE, default=0.0, return_dtype=pl.Float64).alias("own_status"),
        pl.col("practice").replace_strict(PRACTICE_CODE, default=None, return_dtype=pl.Float64).alias("own_practice"),
        *groups,
        (pl.col("status").is_not_null() & ~pl.col("body").is_in([b for v in BODY_GROUPS.values() for b in v]).fill_null(False))
        .cast(pl.Float64)
        .alias("own_other"),
    )
    joined = targets.join(rows, on=KEY, how="left")
    return joined.with_columns(pl.col(c).fill_null(0.0) for c in OWN_COLS if c != "own_practice")


def permuted(frame: pl.DataFrame, cols: list[str], seed: int = PLACEBO_SEED) -> pl.DataFrame:
    """The columns shuffled together within season, week and position."""
    rng = np.random.default_rng(seed)
    idx = frame.with_row_index("_i")
    order = idx.sort("season", "week", "position", "_i")
    shuffled = (
        idx.select("season", "week", "position", *cols)
        .with_columns(pl.Series("_r", rng.random(frame.height)))
        .sort("season", "week", "position", "_r")
    )
    return order.drop(cols).with_columns(*shuffled.select(cols).get_columns()).sort("_i").drop("_i")


# ---- models -----------------------------------------------------------------------------------


def walk_e(rows: pl.DataFrame, extra: list[str], seasons: list[int]) -> pl.DataFrame:
    """KEYS, E for every row of `seasons` (stat-line rows and stat-less ones), each season from
    the production model plus `extra` columns trained on stat-line rows of train_seasons."""
    train_rows = rows.filter(pl.col("statline") == 1.0)
    available = sorted(train_rows["season"].unique().to_list())

    def x(frame: pl.DataFrame) -> np.ndarray:
        base = learn.design(frame, True, vacancy=False)  # vac columns come in through `extra`
        if not extra:
            return base
        return np.hstack([base, frame.select(pl.col(extra).cast(pl.Float64)).to_numpy()])

    parts = []
    for season in seasons:
        train = train_rows.filter(pl.col("season").is_in(train_seasons(season, available)))
        test = rows.filter(pl.col("season") == season)
        pred = learn.fit_predict(x(train), train["points"].to_numpy(), x(test))
        parts.append(test.select(KEYS).with_columns(pl.Series("e", pred)))
    return pl.concat(parts)


def walk_q(feats: pl.DataFrame, extra: list[str], seasons: list[int]) -> pl.DataFrame:
    """KEY, q per played game of `seasons`, stat_line's classifier with `extra` columns added."""
    usable = feats.filter(pl.col("season") >= stat_line.FIRST_PROJECTED_SEASON)
    available = sorted(usable["season"].unique().to_list())
    saved = stat_line.FEATURES
    stat_line.FEATURES = [*saved, *extra]  # design() reads the module list
    try:
        parts = []
        for season in seasons:
            train = usable.filter(pl.col("season").is_in(train_seasons(season, available)))
            test = usable.filter(pl.col("season") == season)
            parts.append(test.select(KEY).with_columns(pl.Series("q", stat_line.fit_predict(train, test))))
    finally:
        stat_line.FEATURES = saved
    return pl.concat(parts)


# ---- layers -----------------------------------------------------------------------------------


def outlook_layer(
    frame: pl.DataFrame, raw: dict[str, pl.DataFrame], held_out: int, vacancy: bool
) -> pl.Series:
    """Outlook-adjusted `proj` (frame: one league, KEY, position, team, proj, points, scored
    season `held_out`), effects estimated on FIRST_CLEAN..held_out-1 of the same frame."""
    stats, team_stats, injuries, games = raw["stats"], raw["team_stats"], raw["injuries"], raw["team_games"]
    base = frame.select(*KEY, "position", "team", pl.col("proj").alias("projection"))
    fit_rows = base.filter(pl.col("season").is_between(FIRST_CLEAN, held_out - 1))
    fit_panel = out.build_panel(
        stats, team_stats, injuries.filter(pl.col("season") < held_out), games, raw["pp"], fit_rows
    )
    effects = out.estimate(fit_panel)
    if not vacancy:
        effects = effects.filter(~pl.col("kind").is_in(["vac_target", "vac_carry"]))
    test_rows = base.filter(pl.col("season") <= held_out)  # earlier games set the return gaps
    panel = out.build_panel(
        stats, team_stats, injuries, games, frame.select(*KEY, "points"), test_rows
    ).filter(pl.col("season") == held_out)
    return layers_check.outlook_prediction(panel, effects).select(*KEY, "outlook_pred")


def perf_factors(frame: pl.DataFrame, raw: dict[str, pl.DataFrame], report: pl.DataFrame, held_out: int) -> pl.DataFrame:
    """Play-through ratio for each row of season `held_out` (1.0 when not listed), the injury
    table fit on FIRST_CLEAN..held_out-1 against the frame's E."""
    proj = frame.filter(pl.col("season").is_between(FIRST_CLEAN, held_out - 1)).select(*KEY, pl.col("e").alias("proj"))
    panel = inj_stage.build_panel(
        raw["injuries"].filter(pl.col("season") < held_out), raw["stats"], raw["team_games"], raw["pp"], proj
    )
    model = InjuryModel(inj_stage.estimate(panel))
    held = frame.filter(pl.col("season") == held_out).join(
        report.select(*KEY, "status", "practice", "body"), on=KEY, how="left"
    )
    factors = []
    for status, practice, body in held.select("status", "practice", "body").iter_rows():
        curve = model.curve((status, body, practice)) if status is not None else None
        factors.append(1.0 if curve is None else curve[1])
    return held.select(KEY).with_columns(pl.Series("perf", factors, dtype=pl.Float64))


def layered(frame: pl.DataFrame, raw: dict[str, pl.DataFrame], report: pl.DataFrame, outlook: str, perf: bool) -> pl.DataFrame:
    """frame (one league; KEY, position, team, e, q, points) with `pred` = layered q * E for the
    scored seasons. outlook: 'full', 'vacoff' or 'none'."""
    frame = frame.with_columns((pl.col("q") * pl.col("e")).alias("proj"))
    parts = []
    for season in SCORED:
        held = frame.filter(pl.col("season") == season).with_columns(pl.col("proj").alias("pred"))
        if outlook != "none":
            adjusted = outlook_layer(frame, raw, season, outlook == "full")
            held = held.join(adjusted, on=KEY, how="left").with_columns(
                pl.coalesce("outlook_pred", "pred").alias("pred")
            ).drop("outlook_pred")
        if perf:
            held = held.join(perf_factors(frame, raw, report, season), on=KEY, how="left").with_columns(
                pl.col("pred") * pl.col("perf").fill_null(1.0)
            ).drop("perf")
        parts.append(held.with_columns(pl.col("pred").clip(lower_bound=0.0)))
    return pl.concat(parts)


# ---- scoring ----------------------------------------------------------------------------------


def rmse(d: pl.DataFrame, col: str) -> float:
    return float(np.sqrt(((d["points"] - d[col]) ** 2).mean()))  # type: ignore[operator]


def paired_t(d: pl.DataFrame, cand: str, ref: str) -> float:
    by_week = d.group_by("season", "week").agg(
        ((pl.col("points") - pl.col(ref)) ** 2).mean().alias("a"),
        ((pl.col("points") - pl.col(cand)) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    return float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else float("nan")


def gain(d: pl.DataFrame, cand: str, ref: str) -> float:
    r = rmse(d, ref)
    return round(100 * (r - rmse(d, cand)) / r, 3) if d.height else float("nan")


def score(d: pl.DataFrame, cand: str, ref: str) -> dict[str, object]:
    row: dict[str, object] = {
        "n": d.height,
        "rmse": round(rmse(d, cand), 4),
        "rmse_ref": round(rmse(d, ref), 4),
        "gain%": gain(d, cand, ref),
        "t": round(paired_t(d, cand, ref), 2),
    }
    for s in SCORED:
        part = d.filter(pl.col("season") == s)
        row[f"t{s}"] = round(paired_t(part, cand, ref), 2)
    for p in SKILL:
        row[p] = gain(d.filter(pl.col("position") == p), cand, ref)
    row["tm_out%"] = gain(d.filter(pl.col("tm_out")), cand, ref)
    row["n_tm_out"] = d.filter(pl.col("tm_out")).height
    return row


# ---- data -------------------------------------------------------------------------------------


def load() -> tuple[dict[str, pl.DataFrame], dict[str, pl.DataFrame], pl.DataFrame, pl.DataFrame]:
    """Per league rows (history and stat-less, with features), raw tables, report, q features."""
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    points = store.read_table("player_points")
    snaps = store.read_table("nfl_snaps", "raw")
    stats = store.read_table("nfl_player_stats", "raw")
    team_stats = store.read_table("nfl_team_stats", "raw")
    injuries = store.read_table("nfl_injuries", "raw")
    team_games = store.read_table("team_games")
    extras = learn.load_extras()
    exp = expected_frame(opp, points, leagues)
    games_all = learn.games_frame(exp, opp, snaps, stats)
    played = stat_line.played_rows(points, exp, snaps, opp)
    report = report_table(injuries)
    usage = extras.usage  # the shipped definitions
    weights = extras.sit_weights
    raw = {"stats": stats, "team_stats": team_stats, "injuries": injuries, "team_games": team_games,
           "snaps": snaps, "usage": usage, "depth": extras.depth}  # fmt: skip
    raw["weights"] = pl.DataFrame({"practice": list(weights), "w": list(weights.values())})
    rows = {}
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        state = learn.state_frame(games)
        hist = learn.build_features(history_targets(exp.filter(pl.col("league_id") == lid)), state, team_games, extras)
        hist = hist.join(games.select(*KEYS, "points"), on=KEYS).with_columns(statline=pl.lit(1.0))
        less = learn.build_features(stat_line.statless_targets(played, lid), state, team_games, extras)
        less = less.with_columns(statline=pl.lit(0.0), points=pl.lit(None, pl.Float64))
        both = pl.concat([hist, less], how="diagonal_relaxed")
        # vac columns: the shipped ones, already added by learn.build_features
        both = own_features(both, report)
        pp = points.filter(pl.col("league_id") == lid).select(*KEY, pl.col("points").alias("pp"))
        rows[lid] = both.join(pp, on=KEY, how="left").with_columns(
            pl.coalesce("points", "pp").fill_null(0.0).alias("points")  # training target unchanged
        ).drop("pp")
    raw["pp_all"] = points
    history = stat_line.history_table(played, stat_line.usage_frame(opp, snaps, stats))
    qfeats = own_features(stat_line.features(played, history, extras.depth), report)
    return rows, raw, report, qfeats


def tm_out_flag(report: pl.DataFrame) -> pl.DataFrame:
    """team, season, week of games where a skill player of the team was listed Out or Doubtful."""
    return (
        report.filter(pl.col("status").is_in(OUT_STATUSES) & pl.col("position").is_in(SKILL))
        .select("team", "season", "week")
        .unique()
        .with_columns(tm_out=pl.lit(True))
    )


def cached(name: str, build, fresh: bool) -> pl.DataFrame:  # type: ignore[no-untyped-def]
    path = SCRATCH / f"{name}.parquet"
    if path.exists() and not fresh:
        return pl.read_parquet(path)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    frame = build()
    frame.write_parquet(path)
    return frame


# ---- serve-time check -------------------------------------------------------------------------


def serve_check(raw: dict[str, pl.DataFrame], report: pl.DataFrame, weights: dict[str | None, float]) -> None:
    """2026 week 7: nflverse final report against Sleeper's status, and the vacancy features each
    gives for the skill players on the week's depth chart."""
    season, week = 2026, 7
    # gsis ids through the crosswalk, as simulate does (the players file lacks most of them)
    sleeper = (
        store.read_table("sleeper_players", "raw")
        .drop("gsis_id")
        .join(store.read_table("id_map").select("sleeper_id", "gsis_id"), on="sleeper_id", how="left")
    )
    snaps = raw["snaps"].filter(pl.col("gsis_id").is_not_null() & pl.col("position").is_in(SKILL))
    teams = (
        snaps.sort("season", "week").group_by("gsis_id").agg(pl.col("team").last(), pl.col("position").last())
    )
    nfl = report.filter((pl.col("season") == season) & (pl.col("week") == week) & pl.col("position").is_in(SKILL))
    slp = vacancy.sleeper_report(sleeper, store.read_table("id_map"), season, week).filter(
        pl.col("position").is_in(SKILL)
    )  # the shipped stand-in: Out only
    on_teams = nfl["team"].unique().to_list()
    both = (
        nfl.select("gsis_id", pl.col("status").fill_null("none").alias("nflverse"))
        .join(slp.filter(pl.col("team").is_in(on_teams)).select("gsis_id", pl.col("status").alias("sleeper")), on="gsis_id", how="full", coalesce=True)
        .with_columns(pl.col("nflverse").fill_null("not listed"), pl.col("sleeper").fill_null("none"))
    )
    print(f"\n== serve-time check, {season} week {week} (Sleeper snapshot of this data copy) ==")
    print(both.group_by("nflverse", "sleeper").len().sort("nflverse", "sleeper"))
    listed = both.filter(pl.col("nflverse").is_in(list(STATUS_CODE)) | pl.col("sleeper").is_in(list(STATUS_CODE)))
    agree = listed.filter(pl.col("nflverse") == pl.col("sleeper")).height
    print(f"game statuses agree on {agree} of {listed.height} players listed by either source")
    chart = raw["depth"].filter((pl.col("season") == season) & (pl.col("week") == week))
    targets = chart.join(teams, on="gsis_id", how="inner").filter(pl.col("team").is_in(on_teams))
    a = vacancy.vacancy_features(targets, nfl, raw["usage"], weights, raw["depth"])
    b = vacancy.vacancy_features(targets, slp, raw["usage"], weights, raw["depth"])
    cmp = a.select(*KEY, *VAC_COLS).join(b.select(*KEY, *VAC_COLS), on=KEY, suffix="_s")
    stats = []
    for c in VAC_COLS:
        d = (cmp[c] - cmp[f"{c}_s"]).abs()
        stats.append({"feature": c, "rows": cmp.height, "differ": int((d > 1e-9).sum()),
                      "mean_abs_diff": round(float(d.mean()), 4),  # type: ignore[arg-type]
                      "mean_nflverse": round(float(cmp[c].mean()), 4)})  # type: ignore[arg-type]
    print(pl.DataFrame(stats))
    own_a = own_features(targets, nfl).select(*KEY, "own_status", "own_practice")
    own_b = own_features(targets, slp.with_columns(pl.lit(None, pl.String).alias("body"))).select(*KEY, "own_status", "own_practice")
    j = own_a.join(own_b, on=KEY, suffix="_s")
    print(f"own_status differs on {int((j['own_status'] != j['own_status_s']).sum())} of {j.height} chart players; "
          f"own_practice known on {int(j['own_practice'].is_not_null().sum())} (nflverse) vs 0 (Sleeper)")


def standin_check(rows: dict[str, pl.DataFrame]) -> None:
    """2026 week 7 played games (those in this copy): RMSE of E from the 2026 model with the vac
    columns from the final report, from Sleeper's Out-only stand-in, and of the model without them."""
    season, week = 2026, 7
    extras = learn.load_extras()
    stand_in = vacancy.sleeper_report(
        store.read_table("sleeper_players", "raw"), store.read_table("id_map"), season, week
    )
    is_week = (pl.col("season") == season) & (pl.col("week") == week)
    alt_report = pl.concat([extras.report.filter(~is_week), stand_in.select(extras.report.columns)])
    print(f"\n== stand-in check, {season} week {week} played games ==")
    for lid, r in rows.items():
        train = r.filter((pl.col("statline") == 1.0) & (pl.col("season") < season))
        test = r.filter(is_week & (pl.col("statline") == 1.0))
        if test.is_empty():
            print(f"{lid}: no played week {week} games in this copy")
            continue
        alt = vacancy.vacancy_features(
            test.drop(VAC_COLS), alt_report, extras.usage, extras.sit_weights, extras.depth
        )
        y = train["points"].to_numpy()
        preds = {
            "final": learn.fit_predict(learn.design(train, True), y, learn.design(test, True)),
            "sleeper_out": learn.fit_predict(learn.design(train, True), y, learn.design(alt, True)),
            "no_vac": learn.fit_predict(
                learn.design(train, True, vacancy=False), y, learn.design(test, True, vacancy=False)
            ),
        }
        pts = test["points"].to_numpy()
        out = {k: round(float(np.sqrt(np.mean((pts - v) ** 2))), 4) for k, v in preds.items()}
        print(f"{lid}: n {test.height}, RMSE {out}")


# ---- main -------------------------------------------------------------------------------------


ARMS = {
    # name: (E extra columns, q extra columns, outlook, perf)
    "base": ([], [], "full", True),
    "base_raw": ([], [], "none", False),
    "vac_b": (VAC_COLS, [], "vacoff", True),
    "vac_c": (VAC_COLS, [], "full", True),
    "vac_raw": (VAC_COLS, [], "none", False),
    "own_b": (OWN_COLS, OWN_COLS, "full", False),
    "own_c": (OWN_COLS, OWN_COLS, "full", True),
    "own_raw": (OWN_COLS, OWN_COLS, "none", False),
    "own_e_raw": (OWN_COLS, [], "none", False),
    "own_q_raw": ([], OWN_COLS, "none", False),
}


def main() -> None:
    fresh = "--fresh" in sys.argv
    rows, raw, report, qfeats = load()
    weights = dict(zip(raw["weights"]["practice"], raw["weights"]["w"], strict=True))
    serve_check(raw, report, weights)
    standin_check(rows)
    if "--serve-only" in sys.argv:
        return
    seasons = list(range(FIRST_CLEAN, 2027))
    flag = tm_out_flag(report)
    q_sets = {
        "q_base": lambda: walk_q(qfeats, [], seasons),
        "q_own": lambda: walk_q(qfeats, OWN_COLS, seasons),
        "q_own_pl": lambda: walk_q(permuted(qfeats, OWN_COLS), OWN_COLS, seasons),
    }
    qs = {name: cached(name, build, fresh) for name, build in q_sets.items()}
    protocol = pbp.scored_rows()
    leagues = store.read_table("leagues", "raw")
    names = dict(zip(leagues["league_id"], leagues["league_key"], strict=True))
    results: dict[str, dict[str, pl.DataFrame]] = {}
    played_scores: list[dict[str, object]] = []
    proto_scores: list[dict[str, object]] = []
    e_cache: dict[tuple[str, str], pl.DataFrame] = {}

    def e_for(lid: str, cols: list[str], placebo: bool) -> pl.DataFrame:
        tag = ("pl_" if placebo else "") + ("+".join(sorted(cols)) or "base")
        key = (lid, tag)
        if key not in e_cache:
            frame = permuted(rows[lid], cols) if placebo else rows[lid]
            e_cache[key] = cached(f"e_{lid}_{hashlib.md5(tag.encode()).hexdigest()[:10]}", lambda: walk_e(frame, cols, seasons), fresh)
        return e_cache[key]

    def run_arm(name: str, e_cols: list[str], q_name: str, outlook: str, perf: bool, placebo: bool) -> None:
        results[name] = {}
        for lid in rows:
            e = e_for(lid, e_cols, placebo)
            frame = (
                rows[lid].select(*KEYS, "position", "team", "points", "statline")
                .join(e, on=KEYS)
                .join(qs[q_name], on=KEY, how="left")
            )
            missing = frame["q"].null_count()
            if missing:
                print(f"{name}: {missing} rows without q, set to 1")
            frame = frame.with_columns(pl.col("q").fill_null(1.0))
            raw_l = {**raw, "pp": raw["pp_all"].filter(pl.col("league_id") == lid).select(*KEY, "points")}
            results[name][lid] = layered(frame, raw_l, report, outlook, perf)

    vac_only = "--vac-only" in sys.argv
    for name, (e_cols, q_cols, outlook, perf) in ARMS.items():
        if vac_only and name.startswith("own"):
            continue
        print(f"arm {name}")
        run_arm(name, e_cols, "q_own" if q_cols else "q_base", outlook, perf, False)

    def mean_rmse(name: str) -> float:
        return float(np.mean([rmse(scored(results[name][lid]), "pred") for lid in rows]))

    def scored(d: pl.DataFrame) -> pl.DataFrame:
        return d.filter((pl.col("season") < 2026) | (pl.col("week") <= LAST_2026_WEEK)).filter(pl.col("week") <= 18)

    vac_layer = "vacoff" if mean_rmse("vac_b") < mean_rmse("vac_c") else "full"
    print(f"vac: (b) outlook without vacancy {mean_rmse('vac_b'):.4f}, (c) full {mean_rmse('vac_c'):.4f}; placebo uses {vac_layer}")
    run_arm("vac_pl", VAC_COLS, "q_base", vac_layer, True, True)
    if not vac_only:
        own_perf = mean_rmse("own_c") < mean_rmse("own_b")
        run_arm("own_pl", OWN_COLS, "q_own_pl", "full", own_perf, True)
        run_arm("both", [*VAC_COLS, *OWN_COLS], "q_own", vac_layer, own_perf, False)
        run_arm("both_pl", [*VAC_COLS, *OWN_COLS], "q_own_pl", vac_layer, own_perf, True)

    PREDS.mkdir(parents=True, exist_ok=True)
    for name, by_league in results.items():
        pl.concat(by_league.values()).select(*KEYS, pl.col("pred").alias("projection")).write_parquet(
            PREDS / f"news_{name}.parquet"
        )
    comparisons = [
        ("vac_b", "base"), ("vac_c", "base"), ("vac_c", "vac_b"), ("vac_pl", "base"), ("vac_raw", "base_raw"),
        ("own_b", "base"), ("own_c", "base"), ("own_pl", "base"), ("own_raw", "base_raw"),
        ("own_e_raw", "base_raw"), ("own_q_raw", "base_raw"), ("both", "base"), ("both_pl", "base"),
    ]  # fmt: skip
    comparisons = [(c, r) for c, r in comparisons if c in results and r in results]
    for cand, ref in comparisons:
        for lid in rows:
            d = (
                scored(results[cand][lid]).select(*KEYS, "position", "team", "points", pl.col("pred").alias("c"), pl.col("e").alias("ce"))
                .join(scored(results[ref][lid]).select(*KEYS, pl.col("pred").alias("r"), pl.col("e").alias("re")), on=KEYS)
                .join(flag, on=["team", "season", "week"], how="left")
                .with_columns(pl.col("tm_out").fill_null(False))
            )
            played_scores.append({"cand": cand, "ref": ref, "league": names[lid], **score(d, "c", "r")})
            p = d.join(protocol.filter(pl.col("league_id") == lid).select(KEYS), on=KEYS, how="semi")
            proto_scores.append({"cand": cand, "ref": ref, "league": names[lid], **score(p, "ce", "re")})
    played_df, proto_df = pl.DataFrame(played_scores), pl.DataFrame(proto_scores)
    print("\n== played games: layered q * E (gain% = drop in RMSE against ref) ==")
    print(played_df)
    print("\n== protocol rows: raw E ==")
    print(proto_df.select("cand", "ref", "league", "n", "rmse", "rmse_ref", "gain%", "t", "t2024", "t2025", "t2026"))
    played_df.write_csv(SCRATCH / "played.csv")
    proto_df.write_csv(SCRATCH / "protocol.csv")
    print("\n== ship rule ==")
    for cand, placebo in (("vac_b", "vac_pl"), ("vac_c", "vac_pl"), ("own_b", "own_pl"), ("own_c", "own_pl"), ("both", "both_pl")):
        if cand not in results:
            continue
        mine = played_df.filter((pl.col("cand") == cand) & (pl.col("ref") == "base"))
        plac = played_df.filter((pl.col("cand") == placebo) & (pl.col("ref") == "base"))
        prot = proto_df.filter((pl.col("cand") == cand) & (pl.col("ref") == "base"))
        checks = {
            "lower both": bool((mine["gain%"] > 0).all()),
            "|t|>=2 one": bool((mine["t"].abs() >= MIN_T).any()),
            "no season t<=-1": bool(all((mine[f"t{s}"] > -1).all() for s in SCORED)),
            "beats placebo": bool((mine["rmse"].to_numpy() < plac["rmse"].to_numpy()).all()),
            "protocol ok": bool((prot["gain%"] >= -MAX_PROTOCOL_LOSS).all()),
        }
        print(f"{cand}: {'SHIPS' if all(checks.values()) else 'fails'} {checks}")


if __name__ == "__main__":
    main()
