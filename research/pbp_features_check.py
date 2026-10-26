"""Do play-by-play, FTN charting, combine or contract data add held-out accuracy to the learned model?

Idea 10 of the 2026-10-25 projection memo. The base is the production model exactly
(`learn.build_features`, `learn.design`, `learn.fit_predict`, `learn.train_seasons`); each
candidate's columns are appended to its design matrix and the model is refit walk-forward. Scored
on 2024, 2025 and 2026 (weeks with results) on the rows `learn.compare_to_baseline` uses (has
history, size-calibrated baseline above 3 points), each league separately. Every candidate also
runs with its values permuted within season and position (placebo): a real gain must clear it.

  redzone   player share of team carries and of team targets inside the 20 (play by play)
  goalline  the same inside the 5
  neutral   team pass rate on first and second down with win probability 0.2 to 0.8
  ftn       FTN charting (2022 on; "FTN Data via nflverse", CC BY-SA 4.0): team play-action,
            motion, screen and no-huddle rates; player catchable, contested and drop shares of
            targets. Base and candidate both train on 2022 on only.
  combine   forty time, weight and speed score (weight * 200 / forty^4), static per player
  contracts APY share of the cap, inflated APY and guarantees of the latest contract signed
            before the season (a placebo: should add nothing beyond draft pick and age)

Lagged columns use `learn.lag_asof` (half-life 4, strictly earlier games, shift 0 = one game
ahead). Downloads are cached under research/scratch/pbp_track/ (gitignored). Combine and contract
data have no stated licence: private use, never committed.

Run from the repo root (data/ must hold the tables):
    OMP_NUM_THREADS=3 uv run python research/pbp_features_check.py [candidate ...] [--repro]
A candidate name may join several with '+', e.g. redzone+neutral.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import nflreadpy as nfl
import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages import learn
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.project import GROUP, expected_frame, history_targets

SCRATCH = Path(__file__).resolve().parent / "scratch" / "pbp_track"
SEASONS = list(range(2018, 2027))
SCORED = (2024, 2025, 2026)
FTN_FIRST = 2022
KEYS = [*GROUP, "season", "week"]
POSITIONS = ("QB", "RB", "WR", "TE")
LOW_GAMES = 4
PLACEBO_SEED = 7


def cached(name: str, build: Callable[[], pl.DataFrame]) -> pl.DataFrame:
    path = SCRATCH / f"{name}.parquet"
    if path.exists():
        return pl.read_parquet(path)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    frame = build()
    frame.write_parquet(path)
    return frame


def per_season(load: Callable[[list[int]], pl.DataFrame], seasons: list[int]) -> pl.DataFrame:
    """Loads season by season and skips only the current season if it is not published."""
    parts = []
    for s in seasons:
        try:
            parts.append(load([s]))
        except Exception as err:
            if s != seasons[-1]:
                raise
            print(f"{s} not loaded: {type(err).__name__}")
    return pl.concat(parts, how="diagonal_relaxed")


PBP_COLS = [
    "game_id", "play_id", "season", "week", "season_type", "posteam", "down", "wp", "pass",
    "rush", "yardline_100", "rusher_player_id", "receiver_player_id", "passer_player_id",
    "pass_attempt", "rush_attempt", "qb_dropback", "two_point_attempt",
]  # fmt: skip


def pbp() -> pl.DataFrame:
    return cached(
        "pbp",
        lambda: per_season(lambda s: nfl.load_pbp(s).select(PBP_COLS), SEASONS).filter(
            (pl.col("season_type") == "REG")
            & pl.col("posteam").is_not_null()
            & (pl.col("two_point_attempt").fill_null(0) == 0)
        ),
    )


# ---- the production model's rows ------------------------------------------------------------


def league_histories() -> dict[str, pl.DataFrame]:
    """Per league: learn.run's history feature rows with points (one game ahead)."""
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = learn.games_frame(
        exp,
        opp,
        store.read_table("nfl_snaps", "raw"),
        store.read_table("nfl_player_stats", "raw"),
    )
    lines = store.read_table("team_games")
    extras = learn.load_extras()
    out = {}
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        targets = history_targets(exp.filter(pl.col("league_id") == lid))
        out[lid] = learn.build_features(targets, learn.state_frame(games), lines, extras).join(
            games.select(*KEYS, "points"), on=KEYS
        )
    return out


def scored_rows() -> pl.DataFrame:
    """The rows `learn.compare_to_baseline` scores, with the calibrated baseline."""
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    history = residual_frame(baseline, store.read_table("player_points"))
    parts = []
    for (lid,), base in baseline.group_by("league_id"):
        for season in SCORED:
            curves = estimate_curves(
                history.filter((pl.col("league_id") == lid) & (pl.col("season") < season))
            )
            cal = apply_curves(base.filter(pl.col("season") == season), curves)
            parts.append(
                cal.filter(pl.col("has_history") & (pl.col("projection") > learn.MIN_PROJECTION))
                .select(*KEYS, pl.col("projection").alias("baseline"))
            )
    return pl.concat(parts)


def walk(
    history: pl.DataFrame,
    extra: list[str],
    seasons: tuple[int, ...] = SCORED,
    first_train: int | None = None,
    drop: tuple[str, ...] = (),
) -> pl.DataFrame:
    """Walk-forward predictions of the production model with `extra` columns appended and the
    `drop` columns of the production design removed."""
    available = sorted(history["season"].unique().to_list())
    names = [*learn.STATE_FEATURES, "week", "is_qb", "is_rb", "is_wr"]
    names += learn.LINE_FEATURES + learn.EXTRA_FEATURES  # learn.design's column order
    keep = [i for i, n in enumerate(names) if n not in drop]

    def x(frame: pl.DataFrame) -> np.ndarray:
        base = learn.design(frame, True)
        assert base.shape[1] == len(names), "learn.design columns changed"
        base = base[:, keep]
        if not extra:
            return base
        return np.hstack([base, frame.select(pl.col(extra).cast(pl.Float64)).to_numpy()])

    parts = []
    for season in seasons:
        allowed = learn.train_seasons(season, available)
        if first_train is not None:
            allowed = [s for s in allowed if s >= first_train]
        train = history.filter(pl.col("season").is_in(allowed))
        test = history.filter(pl.col("season") == season)
        pred = learn.fit_predict(x(train), train["points"].to_numpy(), x(test))
        parts.append(test.select(*KEYS).with_columns(pl.Series("pred", pred)))
    return pl.concat(parts)


def permuted(frame: pl.DataFrame, cols: list[str], seed: int = PLACEBO_SEED) -> pl.DataFrame:
    """The columns shuffled together within season and position (the placebo)."""
    rng = np.random.default_rng(seed)
    indexed = frame.with_row_index("_i")
    order = indexed.sort("season", "position", "_i")
    shuffled = (
        indexed.select("season", "position", *cols)
        .with_columns(pl.Series("_r", rng.random(frame.height)))
        .sort("season", "position", "_r")
    )
    swapped = order.drop(cols).with_columns(*shuffled.select(cols).get_columns())
    return swapped.sort("_i").drop("_i")


# ---- candidate features ---------------------------------------------------------------------


def redzone_table(plays: pl.DataFrame) -> pl.DataFrame:
    """Per player-game: share of the team's carries and targets inside the 20 and the 5."""
    car = plays.filter((pl.col("rush_attempt") == 1) & pl.col("rusher_player_id").is_not_null())
    tgt = plays.filter((pl.col("pass_attempt") == 1) & pl.col("receiver_player_id").is_not_null())
    game = ["posteam", "season", "week"]
    touches = pl.concat(
        [
            car.select(*game, pl.col("rusher_player_id").alias("gsis_id"), "yardline_100",
                       pl.lit("car").alias("kind")),
            tgt.select(*game, pl.col("receiver_player_id").alias("gsis_id"), "yardline_100",
                       pl.lit("tgt").alias("kind")),
        ]
    )  # fmt: skip
    cols = []
    for zone in (20, 5):
        for kind in ("car", "tgt"):
            cols.append(
                ((pl.col("kind") == kind) & (pl.col("yardline_100") <= zone)).alias(f"{kind}{zone}")
            )
    flags = touches.with_columns(*cols)
    names = ["car20", "tgt20", "car5", "tgt5"]
    player = flags.group_by("gsis_id", *game).agg(pl.col(names).sum())
    team = flags.group_by(*game).agg(pl.col(names).sum().name.suffix("_team"))
    passers = plays.filter(pl.col("passer_player_id").is_not_null()).select(
        pl.col("passer_player_id").alias("gsis_id"), *game
    )  # a passer with no carry still played: his rushing shares are 0
    every = pl.concat([player.select("gsis_id", *game), passers]).unique()
    joined = every.join(player, on=["gsis_id", *game], how="left").join(team, on=game, how="left")
    return joined.select(
        "gsis_id",
        pl.col("season").cast(pl.Int64),
        pl.col("week").cast(pl.Int64),
        *[
            (pl.col(n).fill_null(0) / pl.col(f"{n}_team").replace(0, None)).alias(f"{n}_share")
            for n in names
        ],
    ).unique(learn.KEY)


def neutral_table(plays: pl.DataFrame) -> pl.DataFrame:
    """Per team-game: pass rate on first and second down with win probability 0.2 to 0.8."""
    neutral = plays.filter(
        pl.col("down").is_in([1.0, 2.0])
        & pl.col("wp").is_between(0.2, 0.8)
        & ((pl.col("pass") == 1) | (pl.col("rush") == 1))
    )
    return neutral.group_by(pl.col("posteam").alias("team"), "season", "week").agg(
        pl.col("pass").mean().alias("pass_rate")
    ).with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))


def ftn_tables(plays: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """FTN team rates per game and player target shares per game."""
    ftn = cached(
        "ftn",
        lambda: per_season(nfl.load_ftn_charting, list(range(FTN_FIRST, SEASONS[-1] + 1))),
    )
    flags = ["is_play_action", "is_motion", "is_screen_pass", "is_no_huddle",
             "is_catchable_ball", "is_contested_ball", "is_drop"]  # fmt: skip
    charted = ftn.select(
        pl.col("nflverse_game_id").alias("game_id"),
        pl.col("nflverse_play_id").cast(pl.Float64).alias("play_id"),
        *[pl.col(f).cast(pl.Float64) for f in flags],
    ).unique(["game_id", "play_id"])
    joined = plays.with_columns(pl.col("play_id").cast(pl.Float64)).join(
        charted, on=["game_id", "play_id"], how="inner"
    )
    print(f"ftn: {joined.height} plays matched of {charted.height} charted")
    snaps = joined.filter((pl.col("pass") == 1) | (pl.col("rush") == 1))
    team = snaps.group_by(pl.col("posteam").alias("team"), "season", "week").agg(
        pl.col("is_play_action").filter(pl.col("qb_dropback") == 1).mean().alias("pa_rate"),
        pl.col("is_motion").mean().alias("motion_rate"),
        pl.col("is_screen_pass").filter(pl.col("pass_attempt") == 1).mean().alias("screen_rate"),
        pl.col("is_no_huddle").mean().alias("nohuddle_rate"),
    )
    targets = joined.filter(
        (pl.col("pass_attempt") == 1) & pl.col("receiver_player_id").is_not_null()
    )
    player = targets.group_by(pl.col("receiver_player_id").alias("gsis_id"), "season", "week").agg(
        pl.col("is_catchable_ball").mean().alias("catchable"),
        pl.col("is_contested_ball").mean().alias("contested"),
        pl.col("is_drop").mean().alias("drop"),
    )
    cast = [pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64)]
    return team.with_columns(*cast), player.with_columns(*cast)


def combine_table() -> pl.DataFrame:
    """Static per player: forty, weight and speed score from the combine."""
    ids = nfl.load_ff_playerids().select("pfr_id", "gsis_id").drop_nulls().unique("pfr_id")
    raw = cached("combine", nfl.load_combine)
    return (
        raw.join(ids, on="pfr_id", how="inner")
        .select(
            "gsis_id",
            pl.col("forty").cast(pl.Float64).alias("forty"),
            pl.col("wt").cast(pl.Float64).alias("weight"),
        )
        .with_columns((pl.col("weight") * 200 / pl.col("forty") ** 4).alias("speed"))
        .unique("gsis_id", keep="first")
    )


def contracts_table() -> pl.DataFrame:
    raw = cached("contracts", lambda: nfl.load_contracts().drop("season_history", "contract_history"))
    return raw.filter(pl.col("gsis_id").is_not_null() & pl.col("year_signed").is_not_null()).select(
        "gsis_id",
        pl.col("year_signed").cast(pl.Int64),
        pl.col("apy_cap_pct").cast(pl.Float64).alias("apy_cap"),
        pl.col("inflated_apy").cast(pl.Float64).alias("apy_infl"),
        pl.col("inflated_guaranteed").cast(pl.Float64).alias("gtd_infl"),
    ).sort("gsis_id", "year_signed").unique(["gsis_id", "year_signed"], keep="last")


def with_contract(frame: pl.DataFrame, table: pl.DataFrame) -> pl.DataFrame:
    """The latest contract signed in an earlier year than the target season (an in-season
    extension signed in the target year would carry that season's performance)."""
    left = frame.with_columns((pl.col("season") - 1).alias("_cut")).sort("_cut")
    return left.join_asof(
        table.sort("year_signed"),
        left_on="_cut",
        right_on="year_signed",
        by="gsis_id",
        strategy="backward",
        check_sortedness=False,
    ).drop("_cut", "year_signed")


Attach = Callable[[pl.DataFrame], tuple[pl.DataFrame, list[str]]]


def candidates() -> dict[str, tuple[Attach, int | None]]:
    """name -> (adds the columns to a history frame, first training season or None)."""
    plays = pbp()
    rz = redzone_table(plays)
    rz_cols = ["car20_share", "tgt20_share", "car5_share", "tgt5_share"]
    neu = neutral_table(plays)
    team_ftn, player_ftn = ftn_tables(plays)
    comb = combine_table()
    con = contracts_table()

    def redzone(h: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        cols = rz_cols[:2]
        return learn.lag_asof(h, rz, "gsis_id", cols, "rz"), [f"rz_{c}" for c in cols]

    def goalline(h: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        cols = rz_cols[2:]
        return learn.lag_asof(h, rz, "gsis_id", cols, "gl"), [f"gl_{c}" for c in cols]

    def neutral(h: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        return learn.lag_asof(h, neu, "team", ["pass_rate"], "neu"), ["neu_pass_rate"]

    def ftn(h: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        tc = ["pa_rate", "motion_rate", "screen_rate", "nohuddle_rate"]
        pc = ["catchable", "contested", "drop"]
        out = learn.lag_asof(h, team_ftn, "team", tc, "ftnt")
        out = learn.lag_asof(out, player_ftn, "gsis_id", pc, "ftnp")
        return out, [f"ftnt_{c}" for c in tc] + [f"ftnp_{c}" for c in pc]

    def combine(h: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        return h.join(comb, on="gsis_id", how="left"), ["forty", "weight", "speed"]

    def contracts(h: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        return with_contract(h, con), ["apy_cap", "apy_infl", "gtd_infl"]

    return {
        "redzone": (redzone, None),
        "goalline": (goalline, None),
        "neutral": (neutral, None),
        "ftn": (ftn, FTN_FIRST),
        "combine": (combine, None),
        "contracts": (contracts, None),
    }


# ---- scoring --------------------------------------------------------------------------------


def rmse(e: pl.Series) -> float:
    return float(np.sqrt((e**2).mean()))  # type: ignore[operator]


def score(rows: pl.DataFrame, new: str, base: str = "base") -> dict[str, object]:
    """rows: points, position, season, week and the two predictions. Gain is % of base RMSE."""
    e_new, e_base = rows["points"] - rows[new], rows["points"] - rows[base]
    weekly = rows.with_columns(
        ((pl.col("points") - pl.col(base)) ** 2).alias("a"),
        ((pl.col("points") - pl.col(new)) ** 2).alias("b"),
    ).group_by("season", "week").agg(pl.col("a").mean(), pl.col("b").mean())
    diff = (weekly["a"] - weekly["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))

    def gain(mask: pl.Series) -> float:
        b = rmse(e_base.filter(mask))
        return round(100 * (b - rmse(e_new.filter(mask))) / b, 2)

    out: dict[str, object] = {
        "n": rows.height,
        "rmse": round(rmse(e_new), 4),
        "mae": round(float(e_new.abs().mean()), 4),  # type: ignore[arg-type]
        "me": round(-float(e_new.mean()), 3),  # type: ignore[arg-type]  # projection minus points
        "gain%": gain(pl.Series([True] * rows.height)),
        "t": round(t, 2),
        "weeks": f"{int((diff > 0).sum())}/{len(diff)}",
    }
    for s in SCORED:
        out[str(s)] = gain(rows["season"] == s)
    for p in POSITIONS:
        out[p] = gain(rows["position"] == p)
    return out


def evaluate(
    name: str,
    histories: dict[str, pl.DataFrame],
    scored: pl.DataFrame,
    attach: Attach,
    first_train: int | None,
    bases: dict[tuple[str, int | None], pl.DataFrame],
) -> list[dict[str, object]]:
    results = []
    for lid, history in histories.items():
        key = (lid, first_train)
        if key not in bases:
            bases[key] = walk(history, [], first_train=first_train)
        frame, cols = attach(history)
        assert frame.height == history.height, f"{name}: join changed the row count"
        cover = frame.filter(pl.col("season").is_in(SCORED)).select(
            pl.any_horizontal(pl.col(cols).is_not_null()).mean()
        ).item()
        real = walk(frame, cols, first_train=first_train).rename({"pred": "new"})
        placebo = walk(permuted(frame, cols), cols, first_train=first_train).rename(
            {"pred": "placebo"}
        )
        rows = (
            scored.filter(pl.col("league_id") == lid)
            .join(bases[key].rename({"pred": "base"}), on=KEYS)
            .join(real, on=KEYS)
            .join(placebo, on=KEYS)
            .join(frame.select(*KEYS, "position", "points", "n_games"), on=KEYS)
        )
        low = rows.filter(pl.col("n_games") < LOW_GAMES)
        r, p = score(rows, "new"), score(rows, "placebo")
        results.append(
            {
                "candidate": name,
                "league": lid,
                "coverage": round(float(cover), 3),
                **r,
                "placebo_gain%": p["gain%"],
                "placebo_t": p["t"],
                "low_n": low.height,
                "low_gain%": score(low, "new")["gain%"] if low.height > 30 else None,
            }
        )
    return results


def reproduce(histories: dict[str, pl.DataFrame]) -> None:
    """Walk-forward from code against `proj_learned` in data/: max absolute difference."""
    stored = store.read_table("proj_learned").filter(~pl.col("is_future"))
    seasons = tuple(sorted(next(iter(histories.values()))["season"].unique().to_list()))
    for lid, history in histories.items():
        ours = walk(history, [], seasons=seasons)
        mine = stored.filter(pl.col("league_id") == lid).select(*KEYS, "projection")
        both = ours.join(mine, on=KEYS, how="full", coalesce=True)
        diff = (both["pred"] - both["projection"]).abs()
        print(
            f"reproduce {lid}: {ours.height} rows, stored {mine.height}, "
            f"unmatched {both['pred'].null_count() + both['projection'].null_count()}, "
            f"max |diff| {diff.max():.2e}"
        )
        ours.write_parquet(SCRATCH / f"walk_all_{lid}.parquet")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    histories = league_histories()
    if "--repro" in sys.argv:
        reproduce(histories)
    scored = scored_rows()
    table = candidates()
    bases: dict[tuple[str, int | None], pl.DataFrame] = {}
    results = []
    for name in args or list(table):
        parts = [table[n] for n in name.split("+")]

        def attach(h: pl.DataFrame, parts: list = parts) -> tuple[pl.DataFrame, list[str]]:
            cols: list[str] = []
            for add, _ in parts:
                h, c = add(h)
                cols += c
            return h, cols

        first = max((f for _, f in parts if f is not None), default=None)
        results += evaluate(name, histories, scored, attach, first, bases)
        print(pl.DataFrame(results[-2:]))
    out = pl.DataFrame(results)
    out.write_csv(SCRATCH / f"results_{'_'.join(args) or 'all'}.csv")
    with pl.Config(tbl_rows=40, tbl_cols=30, tbl_width_chars=250):
        print(out)


if __name__ == "__main__":
    main()
