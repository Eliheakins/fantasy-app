"""Does shrinking the learned projection toward a position-by-draft-round prior help rookies and
players with few games? (idea 8 of the 2026-10-25 projection memo)

Rows with no history or fewer than 4 earlier games: blended = w * prior + (1 - w) * learned with
w = k / (k + n_games) (the spec; any k > 0 replaces a no-history row by the prior) and a variant
w = k / (k + n_games + 1) (the model's no-history output counts as one game). The prior for
season S is the mean points of such rows (same position and draft round) in seasons before S,
falling back to the position mean for a cell with under MIN_CELL rows. k is chosen on 2021 to
2023 (learned projections from 2019 and 2020 are never used), then scored on 2024 to 2026: on
the low-game rows of the `compare_to_baseline` set, on that whole set, and on the no-history
rows (which that set drops) against actual points. The placebo shuffles the prior within season
and position (draft round information removed).

Run from the repo root after pbp_features_check.py has built its cache:
    OMP_NUM_THREADS=3 uv run python research/shrink_check.py
"""

import numpy as np
import polars as pl
from pbp_features_check import KEYS, LOW_GAMES, PLACEBO_SEED, league_histories, score, scored_rows

from fantasy import store

FIT_SEASONS = (2021, 2022, 2023)
SCORED = (2024, 2025, 2026)
K_GRID = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
MIN_CELL = 30
UNDRAFTED = 300.0


def draft_round(pick: pl.Expr) -> pl.Expr:
    return (
        pl.when(pick.is_null())
        .then(pl.lit("unknown"))
        .when(pick >= UNDRAFTED)
        .then(pl.lit("undrafted"))
        .otherwise(((pick - 1) // 32 + 1).clip(1, 7).cast(pl.Int64).cast(pl.String))
    )


def panel() -> pl.DataFrame:
    """Every history row with the learned projection, games played and draft round."""
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    rows = pl.concat(
        h.select(*KEYS, "position", "points", "n_games", "has_history", "draft_pick")
        for h in league_histories().values()
    )
    return rows.join(learned.select(*KEYS, pl.col("projection").alias("learned")), on=KEYS).with_columns(
        draft_round(pl.col("draft_pick")).alias("round"),
        pl.col("n_games").fill_null(0).alias("n"),
        (pl.col("n_games").is_null() | (pl.col("n_games") < LOW_GAMES)).alias("low"),
    )


def with_prior(rows: pl.DataFrame) -> pl.DataFrame:
    """Adds `prior`: the mean points of low-game rows of earlier seasons in the same cell."""
    low = rows.filter(pl.col("low"))
    parts = []
    for season in sorted(rows["season"].unique().to_list()):
        past = low.filter(pl.col("season") < season)
        if past.is_empty():
            continue
        cell = past.group_by("league_id", "position", "round").agg(
            pl.col("points").mean().alias("cell"), pl.len().alias("cell_n")
        )
        pos = past.group_by("league_id", "position").agg(pl.col("points").mean().alias("pos"))
        parts.append(
            rows.filter(pl.col("season") == season)
            .join(cell, on=["league_id", "position", "round"], how="left")
            .join(pos, on=["league_id", "position"], how="left")
            .with_columns(
                pl.when(pl.col("cell_n") >= MIN_CELL)
                .then(pl.col("cell"))
                .otherwise(pl.col("pos"))
                .alias("prior")
            )
            .drop("cell", "cell_n", "pos")
        )
    return pl.concat(parts)


def shuffled_prior(rows: pl.DataFrame) -> pl.DataFrame:
    rng = np.random.default_rng(PLACEBO_SEED)
    return rows.with_columns(pl.Series("_r", rng.random(rows.height))).with_columns(
        pl.col("prior").sort_by("_r").over("league_id", "season", "position").alias("prior_placebo")
    ).drop("_r")


VARIANTS = {  # name -> (offset, history only)
    "k/(k+n)": (0, False),
    "k/(k+n+1)": (1, False),
    "k/(k+n), history only": (0, True),
}


def blend(k: float, offset: int, history_only: bool, prior: str = "prior") -> pl.Expr:
    w = pl.lit(k) / (pl.lit(k) + pl.col("n") + offset) if k > 0 else pl.lit(0.0)
    eligible = pl.col("low") & pl.col(prior).is_not_null()
    if history_only:
        eligible = eligible & pl.col("has_history")
    return (
        pl.when(eligible)
        .then(w * pl.col(prior) + (1 - w) * pl.col("learned"))
        .otherwise(pl.col("learned"))
    )


def choose_k(fit: pl.DataFrame, offset: int, history_only: bool) -> float:
    errors = {
        k: float(
            np.sqrt(
                fit.select(((pl.col("points") - blend(k, offset, history_only)) ** 2).mean()).item()
            )
        )
        for k in K_GRID
    }
    print(
        f"offset {offset} history_only {history_only}: 2021-2023 low-game RMSE by k "
        + ", ".join(f"{k}: {v:.4f}" for k, v in errors.items())
    )
    return min(errors, key=errors.__getitem__)


def main() -> None:
    rows = shuffled_prior(with_prior(panel()))
    fit = rows.filter(pl.col("season").is_in(FIT_SEASONS) & pl.col("low"))
    test = rows.filter(pl.col("season").is_in(SCORED))
    protocol = scored_rows().select(KEYS)
    results = []
    for variant, (offset, history_only) in VARIANTS.items():
        k = choose_k(fit, offset, history_only)
        scored = test.with_columns(
            blend(k, offset, history_only).alias("new"),
            blend(k, offset, history_only, "prior_placebo").alias("placebo"),
            pl.col("learned").alias("base"),
        )
        on_protocol = scored.join(protocol, on=KEYS)
        sets = {
            "protocol low-game": on_protocol.filter(pl.col("low")),
            "protocol all": on_protocol,
            "no history": scored.filter(~pl.col("has_history")),
            "all low-game": scored.filter(pl.col("low")),
        }
        for name, frame in sets.items():
            for (lid,), part in frame.group_by("league_id"):
                real, placebo = score(part, "new"), score(part, "placebo")
                results.append(
                    {"variant": variant, "k": k, "rows": name, "league": lid, **real,
                     "placebo_gain%": placebo["gain%"], "placebo_t": placebo["t"]}
                )  # fmt: skip
    with pl.Config(tbl_rows=40, tbl_cols=30, tbl_width_chars=250):
        print(pl.DataFrame(results).sort("variant", "rows", "league"))


if __name__ == "__main__":
    main()
