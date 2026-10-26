"""Do role changes add held-out accuracy to the learned model? Depth moves, tenure, roster status.

The base is the production model exactly (`learn.build_features`, `learn.design`,
`learn.fit_predict`, `learn.train_seasons`, with the stat-less played games projected but never
trained on, as `learn.league_projections` does). Each candidate's columns are appended to the
design matrix and the model is refit walk-forward; q (`stat_line` table) is held fixed, so only
E changes. Scored per league:
  played    q * E on every played game (no stat line scores 0), the CLAUDE.md standard
  protocol  E on the `learn.compare_to_baseline` rows
by season, position and the candidate's affected subset, with paired per-week t (critical value
of t for weeks minus 1 degrees of freedom when that is under 30). Placebo: the candidate's columns
shuffled together within season, week and position. Held out 2024, 2025, 2026 weeks 1 to 6.

  depth_prev  the depth rank on the chart of the player's previous game and the change to this
              week's (all seasons)
  kick25      pre-kickoff chart (2025 on, dated snapshots): the rank on the team's last snapshot
              before its own kickoff and the change from the week-start rank the model uses now.
              Fit on 2025 only (base too), scored on 2026 weeks 1 to 6.
  kickall     the same columns, fit on every season (null before 2025), scored on 2026.
  kickfill    as kickall with the week-start rank and a change of 0 before 2025 (added after
              kickall's null columns turned out to act as a season flag; exploratory)
  tenure      games with the current team (current stint), weeks on the roster with that team,
              days since a trade, head coach's games with the team and a new-coach-this-season flag
  status      weeks since the player was last on reserve (IR, PUP) or the practice squad, from
              earlier weeks' roster status only (see `status_timing`: a week's status is stamped
              at that week's game and INA is the game-day inactive list, so the target week's own
              status would leak)

Ship rule (fixed before the runs): played RMSE lower in both leagues, pooled |t| at or above the
critical value in at least one, no season t at or below -1, gain above the placebo's in both,
protocol rows no worse than 0.05%.

Run from the repo root after a `learn` run with stat_line_model on (data/ must hold the tables):
  OMP_NUM_THREADS=3 uv run python research/role_features_check.py [cand ...] [--timing]
    [--preds=DIR]
A candidate may join several with '+'. `--preds` writes each candidate's q * E (league_id, gsis_id,
season, week, projection) for `regret.py`. nflverse downloads are cached in research/scratch/role/.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import nflreadpy as nfl
import numpy as np
import polars as pl
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import bias_check  # noqa: E402

from fantasy import stat_line_table, store  # noqa: E402
from fantasy.stages import learn, stat_line  # noqa: E402
from fantasy.stages.ingest_role import new_depth, schedule_games  # noqa: E402
from fantasy.stages.project import GROUP, expected_frame, history_targets  # noqa: E402
from fantasy.store import SKILL, week_index  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch" / "role"
KEYS = [*GROUP, "season", "week"]
SCORED = (2024, 2025, 2026)
LAST_2026_WEEK = 6
SNAPSHOT_FIRST = 2025
PLACEBO_SEED = 7
MIN_T = 2.0
MAX_PROTOCOL_LOSS = 0.05
RESERVE = ["RES", "PUP"]  # injured reserve, physically unable to perform
RECENT = 4  # weeks or games: the affected subset of the tenure and status candidates
MAX_TRADE_DAYS = 365
pl.Config(tbl_rows=120, tbl_cols=16, tbl_width_chars=220, float_precision=4)


def cached(name: str, build: Callable[[], pl.DataFrame]) -> pl.DataFrame:
    path = SCRATCH / f"{name}.parquet"
    if not path.exists():
        SCRATCH.mkdir(parents=True, exist_ok=True)
        build().write_parquet(path)
    return pl.read_parquet(path)


def ints(*cols: str) -> list[pl.Expr]:
    return [pl.col(c).cast(pl.Int64) for c in cols]


# ---- the production model's rows ------------------------------------------------------------


def panels() -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
    """Per league: history rows (train, with points) and stat-less played rows (never trained on),
    built as `learn.league_projections` builds them; and every played game (KEY, team). Cached:
    delete research/scratch/role/panel_*.parquet after a refresh."""
    leagues = store.read_table("leagues", "raw")
    paths = {lid: SCRATCH / f"panel_{lid}.parquet" for lid in leagues["league_id"].to_list()}
    if all(p.exists() for p in paths.values()) and (SCRATCH / "played.parquet").exists():
        return {lid: pl.read_parquet(p) for lid, p in paths.items()}, pl.read_parquet(
            SCRATCH / "played.parquet"
        )
    opp, points = store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points")
    snaps, stats_raw = (
        store.read_table("nfl_snaps", "raw"),
        store.read_table("nfl_player_stats", "raw"),
    )
    exp = expected_frame(opp, points, leagues)
    played = stat_line.played_rows(points, exp, snaps, opp)
    games_all = learn.games_frame(exp, opp, snaps, stats_raw)
    lines, extras = store.read_table("team_games"), learn.load_extras()
    out = {}
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        state = learn.state_frame(games)
        hist = learn.build_features(
            history_targets(exp.filter(pl.col("league_id") == lid)), state, lines, extras
        ).join(games.select(*KEYS, "points"), on=KEYS)
        extra = learn.build_features(stat_line.statless_targets(played, lid), state, lines, extras)
        out[lid] = pl.concat(
            [hist.with_columns(train=pl.lit(True)), extra.with_columns(train=pl.lit(False))],
            how="diagonal_relaxed",
        )
        out[lid].write_parquet(paths[lid])
    played.write_parquet(SCRATCH / "played.parquet")
    return out, played


def walk(
    panel: pl.DataFrame,
    cols: list[str],
    seasons: tuple[int, ...] = SCORED,
    first_train: int | None = None,
) -> pl.DataFrame:
    """KEYS + E: walk-forward predictions of the production model with `cols` appended."""
    available = sorted(panel.filter(pl.col("train"))["season"].unique().to_list())

    def x(frame: pl.DataFrame) -> np.ndarray:
        base = learn.design(frame, True)
        if not cols:
            return base
        return np.hstack([base, frame.select(pl.col(cols).cast(pl.Float64)).to_numpy()])

    parts = []
    for season in seasons:
        allowed = [
            s
            for s in learn.train_seasons(season, available)
            if first_train is None or s >= first_train
        ]
        train = panel.filter(pl.col("train") & pl.col("season").is_in(allowed))
        test = panel.filter(pl.col("season") == season)
        pred = learn.fit_predict(x(train), train["points"].to_numpy(), x(test))
        parts.append(test.select(KEYS).with_columns(pl.Series("e", pred)))
    return pl.concat(parts)


def permuted(frame: pl.DataFrame, cols: list[str], seed: int = PLACEBO_SEED) -> pl.DataFrame:
    """The columns shuffled together within season, week and position (the placebo)."""
    rng = np.random.default_rng(seed)
    cell = ["season", "week", "position"]
    indexed = frame.with_row_index("_i")
    order = indexed.sort(*cell, "_i")
    shuffled = (
        indexed.select(*cell, *cols)
        .with_columns(pl.Series("_r", rng.random(frame.height)))
        .sort(*cell, "_r")
    )
    return order.drop(cols).with_columns(*shuffled.select(cols).get_columns()).sort("_i").drop("_i")


def scored_frame() -> pl.DataFrame:
    """Played games of the scored weeks: KEYS, position, q, points (0 without a stat line), the
    stored E (proj_learned / q) and the protocol flag."""
    q = stat_line_table.stored()
    if q is None:
        raise SystemExit("run `learn` with stat_line_model = true first")
    learned = store.read_table("proj_learned").filter(
        ~pl.col("is_future")
        & pl.col("season").is_in(SCORED)
        & (pl.col("week") <= 18)
        & ((pl.col("season") < 2026) | (pl.col("week") <= LAST_2026_WEEK))
    )
    e = stat_line_table.divide(learned, q, learn.KEY).select(
        *KEYS, pl.col("projection").alias("stored_e")
    )
    protocol = bias_check.protocol_rows().filter(pl.col("protocol")).select(KEYS)
    points = store.read_table("player_points").select(*KEYS, "points")
    return (
        learned.select(*KEYS, "position")
        .join(e, on=KEYS)
        .join(q, on=learn.KEY)
        .join(points, on=KEYS, how="left")
        .join(protocol.with_columns(protocol=pl.lit(True)), on=KEYS, how="left")
        .with_columns(pl.col("points").fill_null(0.0), pl.col("protocol").fill_null(False))
    )


# ---- candidate features ---------------------------------------------------------------------


def depth_prev(frame: pl.DataFrame) -> pl.DataFrame:
    """The rank on the chart of the player's previous game (as_of_season, as_of_week from the
    state join, strictly before the target) and the change to this week's chart."""
    depth = (
        store.read_table("nfl_depth", "raw")
        .unique(learn.KEY)
        .select(
            "gsis_id",
            pl.col("season").alias("as_of_season"),
            pl.col("week").alias("as_of_week"),
            pl.col("depth_rank").alias("depth_prev"),
        )
    )
    return frame.join(depth, on=["gsis_id", "as_of_season", "as_of_week"], how="left").with_columns(
        (pl.col("depth_rank") - pl.col("depth_prev")).alias("depth_delta")
    )


def snapshots() -> pl.DataFrame:
    return pl.concat(
        [
            cached(f"depth_{s}", lambda s=s: nfl.load_depth_charts([s]))
            for s in range(SNAPSHOT_FIRST, max(SCORED) + 1)
        ],
        how="diagonal_relaxed",
    )


def kickoff_depth() -> pl.DataFrame:
    """KEY, depth_kick: the best skill rank on the team's last snapshot before its own kickoff
    (gameday and gametime are US Eastern; snapshot times are UTC)."""
    sched = store.read_table("nfl_schedules", "raw").filter(
        (pl.col("game_type") == "REG") & (pl.col("season") >= SNAPSHOT_FIRST)
    )
    kick_et = (pl.col("gameday") + " " + pl.col("gametime")).str.to_datetime("%Y-%m-%d %H:%M")
    kicks = (
        pl.concat(
            [
                sched.select("season", "week", pl.col(side).alias("team"), kick_et.alias("kick_et"))
                for side in ("home_team", "away_team")
            ]
        )
        .with_columns(
            pl.col("kick_et")
            .dt.replace_time_zone("America/New_York")
            .dt.convert_time_zone("UTC")
            .dt.replace_time_zone(None)
            .alias("kick")
        )
        .sort("kick")
    )
    snaps = (
        snapshots()
        .filter(pl.col("pos_abb").is_in(SKILL))
        .with_columns(
            pl.col("dt").str.to_datetime(time_zone="UTC").dt.replace_time_zone(None).alias("taken")
        )
    )
    taken = snaps.select("team", "taken").unique().sort("taken")
    picked = kicks.join_asof(
        taken,
        left_on="kick",
        right_on="taken",
        by="team",
        strategy="backward",
        allow_exact_matches=False,
    )
    assert picked["taken"].null_count() == 0, "a team has no snapshot before kickoff"
    assert (picked["taken"] < picked["kick"]).all()
    lag = (picked["kick"] - picked["taken"]).dt.total_hours()
    print(f"kickoff chart taken a median {lag.median():.0f} h (max {lag.max()} h) before kickoff")
    return (
        picked.join(
            snaps.select("team", "taken", "gsis_id", pl.col("pos_rank").cast(pl.Float64)),
            on=["team", "taken"],
        )
        .group_by(learn.KEY)
        .agg(pl.col("pos_rank").min().alias("depth_kick"))
        .with_columns(*ints("season", "week"))
    )


def check_week_start(snaps: pl.DataFrame) -> None:
    """The stored 2025-on depth_rank must be the week-start pick of `ingest_role.new_depth`."""
    mine = new_depth(snaps, schedule_games(list(range(SNAPSHOT_FIRST, max(SCORED) + 1))))
    stored = store.read_table("nfl_depth", "raw").filter(pl.col("season") >= SNAPSHOT_FIRST)
    both = mine.join(stored, on=learn.KEY, how="full", coalesce=True, suffix="_s")
    same = (both["depth_rank"] == both["depth_rank_s"]).sum()
    print(
        f"week-start chart: {same} of {both.height} rows match the stored nfl_depth; missing "
        f"here {both['depth_rank'].null_count()}, stored {both['depth_rank_s'].null_count()}"
    )


def with_kick(frame: pl.DataFrame, kick: pl.DataFrame) -> pl.DataFrame:
    return frame.join(kick, on=learn.KEY, how="left").with_columns(
        (pl.col("depth_kick") - pl.col("depth_rank")).alias("depth_kick_delta")
    )


def stint(by: str, value: str) -> pl.Expr:
    """A counter that steps each time `value` changes within `by` (frame sorted by by, t)."""
    return (
        (pl.col(value) != pl.col(value).shift(1)).fill_null(True).cast(pl.Int64).cum_sum().over(by)
    )


def tenure_tables(played: pl.DataFrame) -> dict[str, pl.DataFrame]:
    games = (
        played.select(learn.KEY + ["team"])
        .with_columns(week_index().alias("t"))
        .sort("gsis_id", "t")
    )
    games = (
        games.with_columns(stint("gsis_id", "team").alias("_s"))
        .with_columns(pl.int_range(1, pl.len() + 1).over("gsis_id", "_s").alias("stint_games"))
        .select("gsis_id", "t", pl.col("team").alias("last_team"), "stint_games")
    )
    ros = cached(
        "rosters_weekly",
        lambda: pl.concat(
            [nfl.load_rosters_weekly([s]) for s in range(2018, max(SCORED) + 1)],
            how="diagonal_relaxed",
        ),
    )
    ros = (
        ros.filter((pl.col("game_type") == "REG") & pl.col("gsis_id").is_not_null())
        .select("gsis_id", *ints("season", "week"), "team", "status", "full_name")
        .unique(learn.KEY)
        .with_columns(week_index().alias("t"))
        .sort("gsis_id", "t")
    )
    on_team = (
        ros.with_columns(stint("gsis_id", "team").alias("_s"))
        .with_columns(pl.int_range(0, pl.len()).over("gsis_id", "_s").alias("roster_weeks"))
        .select("gsis_id", "t", pl.col("team").alias("ros_team"), "roster_weeks")
    )
    sched = cached("schedules", lambda: nfl.load_schedules(list(range(2018, max(SCORED) + 1))))
    sched = sched.filter(pl.col("game_type") == "REG")
    coach = (
        pl.concat(
            [
                sched.select(
                    *ints("season", "week"),
                    pl.col(f"{s}_team").alias("team"),
                    pl.col(f"{s}_coach").alias("coach"),
                    "gameday",
                )
                for s in ("home", "away")
            ]
        )
        .with_columns(week_index().alias("t"))
        .sort("team", "t")
    )
    coach = (
        coach.with_columns(stint("team", "coach").alias("_s"))
        .with_columns(
            pl.int_range(0, pl.len()).over("team", "_s").alias("hc_games"),
            pl.col("season").min().over("team", "_s").alias("_first"),
        )
        .with_columns((pl.col("_first") == pl.col("season")).cast(pl.Float64).alias("new_hc"))
    )
    ids = (
        cached("ff_playerids", nfl.load_ff_playerids)
        .select("pfr_id", "gsis_id")
        .drop_nulls()
        .unique("pfr_id")
    )
    trades = (
        cached("trades", nfl.load_trades)
        .filter(pl.col("pfr_id").is_not_null())
        .join(ids, on="pfr_id")
        .select("gsis_id", pl.col("trade_date").cast(pl.Date))
        .unique()
        .sort("trade_date")
    )
    return {"games": games, "on_team": on_team, "coach": coach, "trades": trades, "rosters": ros}


def tenure(frame: pl.DataFrame, tabs: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Games in the current stint with the target team before the target (0 when his last game was
    for another team or he has none), roster weeks with the team up to the target week, days since
    his latest trade before game day, the head coach's earlier games with the team and new_hc."""
    left = frame.with_columns(week_index().alias("t")).sort("t")
    out = left.join_asof(
        tabs["games"].sort("t"),
        on="t",
        by="gsis_id",
        strategy="backward",
        allow_exact_matches=False,
        check_sortedness=False,
    )
    out = out.join_asof(
        tabs["on_team"].sort("t"), on="t", by="gsis_id", strategy="backward", check_sortedness=False
    )
    coach = tabs["coach"].select(
        "season", "week", "team", "hc_games", "new_hc", pl.col("gameday").str.to_date().alias("day")
    )
    out = out.join(coach, on=["season", "week", "team"], how="left").sort("day")
    out = out.join_asof(
        tabs["trades"].rename({"trade_date": "_td"}),
        left_on="day",
        right_on="_td",
        by="gsis_id",
        strategy="backward",
        allow_exact_matches=False,
        check_sortedness=False,
    )
    days = (pl.col("day") - pl.col("_td")).dt.total_days().cast(pl.Float64)
    return out.with_columns(
        pl.when(pl.col("last_team") == pl.col("team"))
        .then(pl.col("stint_games"))
        .otherwise(0)
        .cast(pl.Float64)
        .alias("team_games"),
        pl.when(pl.col("ros_team") == pl.col("team"))
        .then(pl.col("roster_weeks"))
        .otherwise(0)
        .cast(pl.Float64)
        .alias("weeks_on_team"),
        pl.when(days <= MAX_TRADE_DAYS).then(days).otherwise(None).alias("days_since_trade"),
        pl.col("hc_games").cast(pl.Float64),
    ).drop("t", "last_team", "stint_games", "ros_team", "roster_weeks", "day", "_td")


def status(frame: pl.DataFrame, rosters: pl.DataFrame) -> pl.DataFrame:
    """Weeks since his latest reserve (IR, PUP) and practice-squad week this season, from roster
    rows of EARLIER weeks only (null when none)."""
    out = frame.with_columns(week_index().alias("t")).sort("t")
    for name, codes in (("res", RESERVE), ("dev", ["DEV"])):
        rows = (
            rosters.filter(pl.col("status").is_in(codes))
            .select(
                "gsis_id",
                "t",
                pl.col("season").alias(f"_s_{name}"),
                pl.col("week").alias(f"_w_{name}"),
            )
            .sort("t")
        )
        out = out.join_asof(
            rows,
            on="t",
            by="gsis_id",
            strategy="backward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
        out = out.with_columns(
            pl.when(pl.col(f"_s_{name}") == pl.col("season"))
            .then(pl.col("week") - pl.col(f"_w_{name}"))
            .otherwise(None)
            .cast(pl.Float64)
            .alias(f"weeks_since_{name}")
        ).drop(f"_s_{name}", f"_w_{name}")
    return out.drop("t")


# ---- status timing --------------------------------------------------------------------------


def status_timing(rosters: pl.DataFrame) -> None:
    """When is a week's roster status stamped? Against snaps and the Friday injury report."""
    snaps = store.read_table("nfl_snaps", "raw").filter(pl.col("gsis_id").is_not_null())
    field = snaps.group_by(learn.KEY).agg(
        ((pl.col("offense_snaps") + pl.col("st_snaps")).sum() > 0).alias("field")
    )
    inj = cached(
        "injuries",
        lambda: pl.concat(
            [nfl.load_injuries([s]) for s in range(2018, max(SCORED) + 1)], how="diagonal_relaxed"
        ),
    )
    inj = (
        inj.filter(pl.col("game_type") == "REG")
        .select("gsis_id", *ints("season", "week"), "report_status")
        .unique(learn.KEY)
    )
    pos = (
        store.read_table("nfl_snaps", "raw")
        .select("gsis_id", "position")
        .drop_nulls()
        .unique("gsis_id")
    )
    d = (
        rosters.filter(pl.col("season") >= 2019)
        .join(pos.filter(pl.col("position").is_in(SKILL)), on="gsis_id")
        .join(field, on=learn.KEY, how="left")
        .join(inj, on=learn.KEY, how="left")
        .with_columns(pl.col("field").fill_null(False))
    )
    print("-- status timing (skill players, REG, 2019 on): share who took the field that week")
    print(
        d.group_by("status")
        .agg(pl.len().alias("n"), pl.col("field").mean())
        .sort("n", descending=True)
        .head(6)
    )
    print("Questionable on the Friday report: roster status by whether he took the field")
    quest = d.filter(pl.col("report_status") == "Questionable")
    print(quest.group_by("field", "status").len().sort("field", "len"))
    print(
        quest.filter(pl.col("season") == 2025)
        .sort("week")
        .group_by("status", "field")
        .head(3)
        .select("full_name", "team", "season", "week", "report_status", "status", "field")
    )


# ---- scoring --------------------------------------------------------------------------------


def crit(weeks: int) -> float:
    df = weeks - 1
    return MIN_T if df >= 30 else float(stats.t.ppf(0.975, df))


def score(d: pl.DataFrame, a: str, b: str) -> dict[str, object]:
    """Candidate b against reference a; t positive when b is better."""
    if d.height == 0:
        return {"n": 0}
    by_week = d.group_by("season", "week").agg(
        ((pl.col(a) - pl.col("points")) ** 2).mean().alias("a"),
        ((pl.col(b) - pl.col("points")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    sd = diff.std(ddof=1) if len(diff) > 1 else 0.0
    t = float(diff.mean() / (sd / np.sqrt(len(diff)))) if sd > 0 else 0.0
    ra = float(np.sqrt(((d[a] - d["points"]) ** 2).mean()))  # type: ignore[arg-type]
    rb = float(np.sqrt(((d[b] - d["points"]) ** 2).mean()))  # type: ignore[arg-type]
    return {
        "n": d.height,
        "rmse_ref": round(ra, 4),
        "rmse": round(rb, 4),
        "gain_pct": round(100 * (ra - rb) / ra, 3),
        "t": round(t, 2),
        "weeks": f"{int((diff > 0).sum())}/{len(diff)}",
        "crit": round(crit(len(diff)), 2),
    }


def evaluate(
    name: str, rows: pl.DataFrame, affected: pl.Expr, seasons: tuple[int, ...]
) -> tuple[list[dict], bool]:
    """rows: one league set with columns base, cand, plac (E) and q. Report rows and the verdict."""
    rows = rows.with_columns(
        (pl.col("q") * pl.col("base")).alias("qbase"),
        (pl.col("q") * pl.col("cand")).alias("qcand"),
        (pl.col("q") * pl.col("plac")).alias("qplac"),
        affected.fill_null(False).alias("affected"),
    )
    out, checks = [], []
    for (league,), g in rows.group_by("league", maintain_order=True):
        played = score(g, "qbase", "qcand")
        plac = score(g, "qbase", "qplac")
        prot = score(g.filter(pl.col("protocol")), "base", "cand")
        cuts = [("played", "all", played), ("placebo", "all", plac), ("protocol", "all", prot)]
        cuts += [
            ("played", str(s), score(g.filter(pl.col("season") == s), "qbase", "qcand"))
            for s in seasons
        ]
        cuts += [
            ("played", p, score(g.filter(pl.col("position") == p), "qbase", "qcand")) for p in SKILL
        ]
        cuts += [
            ("played", "affected", score(g.filter(pl.col("affected")), "qbase", "qcand")),
            (
                "protocol",
                "affected",
                score(g.filter(pl.col("affected") & pl.col("protocol")), "base", "cand"),
            ),
        ]
        out += [{"cand": name, "league": league, "rows": r, "cut": c, **s} for r, c, s in cuts]
        season_ok = all(
            s["t"] > -1 for r, c, s in cuts if r == "played" and c in map(str, seasons) and s["n"]
        )
        checks.append(
            {
                "lower": played["gain_pct"] > 0,
                "sig": abs(played["t"]) >= played["crit"],
                "season_ok": season_ok,
                "beats_placebo": played["gain_pct"] > plac["gain_pct"],
                "protocol_ok": prot["gain_pct"] >= -MAX_PROTOCOL_LOSS,
            }
        )
    ships = all(
        c["lower"] and c["season_ok"] and c["beats_placebo"] and c["protocol_ok"] for c in checks
    ) and any(c["sig"] for c in checks)
    print(f"{name}: verdict {'SHIPS' if ships else 'does not ship'} {checks}")
    return out, ships


# ---- main -----------------------------------------------------------------------------------


def candidates(
    played: pl.DataFrame,
) -> dict[str, tuple[Callable[[pl.DataFrame], pl.DataFrame], list[str], pl.Expr]]:
    """name -> (adds the columns, the columns, the affected-subset expression)."""
    tabs = tenure_tables(played)
    kick: list[pl.DataFrame] = []

    def add_kick(f: pl.DataFrame) -> pl.DataFrame:
        if not kick:
            kick.append(kickoff_depth())
        return with_kick(f, kick[0])

    moved = pl.col("depth_rank").ne_missing(pl.col("depth_prev"))
    kick_moved = pl.col("depth_kick").ne_missing(pl.col("depth_rank")) & (
        pl.col("season") >= SNAPSHOT_FIRST
    )
    recent = (
        (pl.col("team_games") < RECENT)
        | (pl.col("weeks_on_team") < RECENT)
        | (pl.col("days_since_trade") <= 7 * RECENT)
        | (pl.col("hc_games") < RECENT)
    )
    back = (pl.col("weeks_since_res") <= RECENT) | (pl.col("weeks_since_dev") <= RECENT)

    def add_kick_filled(f: pl.DataFrame) -> pl.DataFrame:
        old = pl.col("season") < SNAPSHOT_FIRST  # no dated charts: no intra-week move
        return add_kick(f).with_columns(
            pl.when(old)
            .then(pl.col("depth_rank"))
            .otherwise(pl.col("depth_kick"))
            .alias("depth_kick"),
            pl.when(old).then(0.0).otherwise(pl.col("depth_kick_delta")).alias("depth_kick_delta"),
        )

    kcols = ["depth_kick", "depth_kick_delta"]
    return {
        "depth_prev": (depth_prev, ["depth_prev", "depth_delta"], moved),
        "kick25": (add_kick, kcols, kick_moved),
        "kickall": (add_kick, kcols, kick_moved),
        "kickfill": (add_kick_filled, kcols, kick_moved),
        "tenure": (
            lambda f: tenure(f, tabs),
            ["team_games", "weeks_on_team", "days_since_trade", "hc_games", "new_hc"],
            recent,
        ),
        "status": (
            lambda f: status(f, tabs["rosters"]),
            ["weeks_since_res", "weeks_since_dev"],
            back,
        ),
    }, tabs


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    preds_dir = next(
        (Path(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--preds=")), None
    )
    panel_by_league, played = panels()
    table, tabs = candidates(played)
    if "--timing" in sys.argv:
        status_timing(tabs["rosters"])
        check_week_start(snapshots())
    names = {
        r["league_id"]: r["name"].split()[0]
        for r in store.read_table("leagues", "raw").iter_rows(named=True)
    }
    scored = scored_frame().with_columns(pl.col("league_id").replace_strict(names).alias("league"))
    bases: dict[tuple[str, int | None], pl.DataFrame] = {}
    report: list[dict] = []
    for name in args or [n for n in table if n not in ("kickall", "kickfill")]:
        parts = [table[n] for n in name.split("+")]
        cols = [c for _, cs, _ in parts for c in cs]
        affected = pl.any_horizontal([a for _, _, a in parts])
        kick_only = name.startswith("kick")
        seasons = (2026,) if kick_only else SCORED
        first = SNAPSHOT_FIRST if name.startswith("kick25") else None
        frames = []
        for lid, panel in panel_by_league.items():
            key = (lid, first, seasons)
            if key not in bases:
                bases[key] = walk(panel, [], seasons, first)
                if first is None and seasons == SCORED:
                    diff = scored.filter(pl.col("league_id") == lid).join(bases[key], on=KEYS)
                    print(
                        f"reproduce {names[lid]}: {diff.height} rows, max |E - stored E| "
                        f"{(diff['e'] - diff['stored_e']).abs().max():.2e}"
                    )
            frame = panel
            for add, _, _ in parts:
                frame = add(frame)
            assert frame.height == panel.height, f"{name}: a join changed the row count"
            cover = (
                frame.filter(pl.col("season").is_in(seasons))
                .select(pl.any_horizontal(pl.col(cols).is_not_null()).mean())
                .item()
            )
            print(f"{name} {names[lid]}: non-null coverage on scored seasons {cover:.3f}")
            cand = walk(frame, cols, seasons, first).rename({"e": "cand"})
            plac = walk(permuted(frame, cols), cols, seasons, first).rename({"e": "plac"})
            frames.append(
                scored.filter(pl.col("league_id") == lid)
                .join(bases[key].rename({"e": "base"}), on=KEYS)
                .join(cand, on=KEYS)
                .join(plac, on=KEYS)
                .join(frame.select(*KEYS, *cols, "depth_rank"), on=KEYS)
            )
        rows = pl.concat(frames)
        out, _ = evaluate(name, rows, affected, seasons)
        report += out
        print(pl.DataFrame(out).drop("cand"))
        if preds_dir is not None:
            preds_dir.mkdir(parents=True, exist_ok=True)
            rows.select(*KEYS, (pl.col("q") * pl.col("cand")).alias("projection")).write_parquet(
                preds_dir / f"role_{name}.parquet"
            )
    pl.DataFrame(report).write_csv(SCRATCH / f"results_{'_'.join(args) or 'all'}.csv")


if __name__ == "__main__":
    main()
