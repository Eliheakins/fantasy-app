from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest

from fantasy import _scorecard as sc
from fantasy.stages import backtest as bt

KICK = datetime(2026, 10, 25, 17, 0, tzinfo=UTC)
KEYS = {"league_id": "L", "season": 2026, "week": 7}


def universe(*players: tuple[str, str]) -> pl.DataFrame:
    return pl.DataFrame([{**KEYS, "gsis_id": g, "team": t, "position": "WR"} for g, t in players])


def snaps(*rows: tuple[str, str, float, float]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {**KEYS, "gsis_id": g, "fetched_at": at, "learned": lo, "baseline": ba}
            for g, at, lo, ba in rows
        ]
    )


def actuals(**points: float) -> pl.DataFrame:
    return pl.DataFrame([{**KEYS, "gsis_id": g, "points": p} for g, p in points.items()])


def kicks(**teams: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        [{"season": 2026, "week": 7, "team": t, "kickoff": k} for t, k in teams.items()],
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "team": pl.String,
            "kickoff": pl.Datetime("us", "UTC"),
        },
    )


def test_picks_the_last_snapshot_before_kickoff_and_ignores_later_ones() -> None:
    out, _ = sc.score_games(
        universe(("a", "X")),
        snaps(
            ("a", "2026-10-24T00:00:00+00:00", 1.0, 1.0),
            ("a", "2026-10-25T16:59:00+00:00", 2.0, 3.0),
            ("a", "2026-10-25T17:01:00+00:00", 9.0, 9.0),  # after kickoff
        ),
        None,
        actuals(a=5.0),
        kicks(X=KICK),
    )
    assert out["learned"].to_list() == [2.0] and out["baseline"].to_list() == [3.0]


def test_counts_each_reason_a_game_is_left_out() -> None:
    out, ex = sc.score_games(
        universe(("ok", "X"), ("open", "X"), ("nokick", "Y"), ("late", "X")),
        snaps(
            ("ok", "2026-10-24T00:00:00+00:00", 1.0, 1.0),
            ("open", "2026-10-24T00:00:00+00:00", 1.0, 1.0),
            ("nokick", "2026-10-24T00:00:00+00:00", 1.0, 1.0),
            ("late", "2026-10-25T18:00:00+00:00", 1.0, 1.0),  # only after kickoff
        ),
        None,
        actuals(ok=4.0, nokick=4.0, late=4.0),
        kicks(X=KICK),
    )
    assert out["gsis_id"].to_list() == ["ok"]
    assert ex == {
        "games": 4, "scored": 1, "not_final": 1, "no_kickoff": 1, "no_snapshot": 1,
        "sleeper_missing": 0,
    }  # fmt: skip


def test_sleeper_is_scored_only_from_its_own_pre_kickoff_snapshot() -> None:
    sleeper = pl.DataFrame(
        [
            {**KEYS, "gsis_id": "a", "fetched_at": "2026-10-24T00:00:00+00:00", "sleeper": 7.0},
            {**KEYS, "gsis_id": "a", "fetched_at": "2026-10-25T17:30:00+00:00", "sleeper": 99.0},
        ]
    )
    out, ex = sc.score_games(
        universe(("a", "X"), ("b", "X")),
        snaps(
            ("a", "2026-10-24T00:00:00+00:00", 1.0, 1.0),
            ("b", "2026-10-24T00:00:00+00:00", 1.0, 1.0),
        ),
        sleeper,
        actuals(a=1.0, b=1.0),
        kicks(X=KICK),
    )
    assert out.sort("gsis_id")["sleeper"].to_list() == [7.0, None]
    assert ex["sleeper_missing"] == 1


def scored(**cols: list) -> pl.DataFrame:
    n = len(cols["actual"])
    base = {"week": pl.Series([7] * n, dtype=pl.Int64), "position": ["WR"] * n, "tier": [0] * n}
    return pl.DataFrame({**base, **cols})


def cell(
    t: pl.DataFrame, model: str, week: int | None = None, position: str = "ALL", tier: int = -1
) -> dict:
    row = t.filter(
        (pl.col("model") == model)
        & (pl.col("week").is_null() if week is None else pl.col("week") == week)
        & (pl.col("position") == position)
        & (pl.col("tier") == tier)
    )
    assert row.height == 1
    return row.row(0, named=True)


def test_error_table_mae_rmse_bias_n() -> None:
    t = sc.error_table(scored(actual=[10.0, 20.0], learned=[12.0, 17.0], baseline=[10.0, 20.0]))
    r = cell(t, "learned")
    assert r["n"] == 2 and r["mae"] == pytest.approx(2.5)
    assert r["rmse"] == pytest.approx(np.sqrt((4 + 9) / 2)) and r["bias"] == pytest.approx(-0.5)
    assert cell(t, "baseline")["mae"] == 0.0


def test_error_table_has_all_weeks_and_per_week_rows_and_skips_a_missing_model() -> None:
    frame = pl.concat(
        [
            scored(actual=[10.0], learned=[8.0]),
            scored(actual=[4.0], learned=[4.0]).with_columns(week=pl.lit(8).cast(pl.Int64)),
        ]
    )
    t = sc.error_table(frame)
    assert set(t["model"]) == {"learned"}
    assert cell(t, "learned", week=7)["mae"] == 2.0
    assert cell(t, "learned", week=None)["n"] == 2


def test_error_table_ignores_rows_where_a_model_has_no_projection() -> None:
    t = sc.error_table(scored(actual=[10.0, 10.0], learned=[8.0, None], baseline=[9.0, 9.0]))
    assert cell(t, "learned")["n"] == 1 and cell(t, "baseline")["n"] == 2


def test_error_table_of_nothing_is_empty_with_the_schema() -> None:
    t = sc.error_table(scored(actual=[], learned=[]))
    assert t.is_empty() and "mae" in t.columns


def test_error_table_matches_the_backtest_metrics() -> None:
    rng = np.random.default_rng(0)
    n = 300
    rows = pl.DataFrame(
        {
            "league_id": ["L"] * n,
            "position": ["WR"] * n,
            "season": [2022] * (n // 2) + [2024] * (n // 2),
            "projection": rng.uniform(0, 20, n),
            "learned": rng.uniform(0, 20, n),
            "points": rng.uniform(0, 30, n),
        }
    )
    m = bt.metrics(rows, 1).filter(pl.col("position") == "WR")
    test = rows.filter(pl.col("season") == 2024)
    train = rows.filter(pl.col("season") == 2022)
    tier = bt.size_tiers(train["projection"].to_numpy(), test["projection"].to_numpy())
    frame = test.select(
        pl.lit(7).alias("week"), "position", pl.Series("tier", tier),
        pl.col("points").alias("actual"),
        pl.col("projection").alias("baseline"), "learned",
    )  # fmt: skip
    t = sc.error_table(frame)
    for tier_id in (-1, 0, 1, 2):
        for model, name in (("baseline", "baseline"), ("learned", "learned")):
            ref = m.filter((pl.col("tier") == tier_id) & (pl.col("forecaster") == name)).row(
                0, named=True
            )
            got = cell(t, model, week=7, position="ALL", tier=tier_id)
            assert got["n"] == ref["n"]
            assert got["mae"] == pytest.approx(ref["mae"])
            assert got["rmse"] == pytest.approx(ref["rmse"])


def test_add_tiers_uses_training_edges_per_league_and_position() -> None:
    train = pl.DataFrame({"league_id": ["L"] * 6, "position": ["WR"] * 6,
                          "projection": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})  # fmt: skip
    frame = pl.DataFrame({"league_id": ["L", "L", "L", "L"], "position": ["WR", "WR", "WR", "TE"],
                          "baseline": [0.5, 3.5, 9.0, 3.0]})  # fmt: skip
    out = sc.add_tiers(frame, train)
    assert out["tier"].to_list() == [0, 1, 2, None]
