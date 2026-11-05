"""Leakage checks for the research-only public-build features (research/public_features.py)."""

import importlib.util
from pathlib import Path

import polars as pl

_PATH = Path(__file__).resolve().parents[1] / "research" / "public_features.py"
_SPEC = importlib.util.spec_from_file_location("public_features", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
pf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pf)


def _usage(week3_inv: float) -> pl.DataFrame:
    rows = [
        ("a", 1, "A", 0.5), ("a", 2, "A", 0.5), ("a", 3, "A", 0.1),
        ("b", 1, "A", 0.1), ("b", 2, "A", 0.1), ("b", 3, "A", week3_inv),
        ("c", 3, "A", 0.9),  # first game in week 3
        ("d", 1, "A", 0.9), ("d", 2, "B", 0.9),  # traded after week 1
    ]  # fmt: skip
    return pl.DataFrame(rows, schema=["gsis_id", "week", "team", "inv"], orient="row").with_columns(
        season=pl.lit(2024), position=pl.lit("WR")
    )


def _schedule() -> pl.DataFrame:
    return pl.DataFrame(
        {"team": ["A"] * 4 + ["B"] * 4, "season": [2024] * 8, "week": [1, 2, 3, 4] * 2}
    )


def _ranks(week3_inv: float, week: int) -> dict[str, float]:
    out = pf.role_rank(_usage(week3_inv), _schedule())
    rows = out.filter((pl.col("team") == "A") & (pl.col("week") == week))
    return dict(zip(rows["gsis_id"], rows["depth_rank"], strict=True))


def test_role_rank_uses_only_earlier_games() -> None:
    # week 3's own involvement must not change week 3's ranks
    assert _ranks(0.1, 3) == _ranks(0.99, 3) == {"a": 1.0, "b": 2.0}


def test_role_rank_sees_the_game_once_it_is_past() -> None:
    assert _ranks(0.99, 4)["b"] < _ranks(0.1, 4)["b"]
    assert "c" in _ranks(0.1, 4)


def test_role_rank_drops_a_player_who_moved_on() -> None:
    assert "d" not in _ranks(0.1, 3)
    out = pf.role_rank(_usage(0.1), _schedule())
    assert out.filter((pl.col("team") == "B") & (pl.col("week") == 3))["gsis_id"].to_list() == ["d"]


def test_involvement_share_counts_dropbacks_carries_and_targets() -> None:
    plays = pl.DataFrame(
        {
            "season": [2024] * 4,
            "week": [1] * 4,
            "season_type": ["REG"] * 4,
            "posteam": ["A"] * 4,
            "pass": [1.0, 1.0, 0.0, 0.0],
            "rush": [0.0, 0.0, 1.0, 1.0],
            "qb_dropback": [1.0, 1.0, 0.0, 0.0],
            "pass_attempt": [1.0, 1.0, 0.0, 0.0],
            "sack": [0.0, 0.0, 0.0, 0.0],
            "complete_pass": [1.0, 0.0, 0.0, 0.0],
            "passer_id": ["q", "q", None, None],
            "rusher_id": [None, None, "r", "r"],
            "receiver_id": ["w", "w", None, None],
            "air_yards": [10.0, 20.0, None, None],
            "yards_after_catch": [5.0, None, None, None],
            "xyac_mean_yardage": [3.0, None, None, None],
            "epa": [1.0, -1.0, 0.5, 0.1],
            "success": [1.0, 0.0, 1.0, 0.0],
            "cpoe": [10.0, -10.0, None, None],
        }
    )
    games = pf.player_games(plays)
    inv = dict(zip(games["gsis_id"], games["inv"], strict=True))
    assert inv == {"q": 0.5, "r": 0.5, "w": 0.5}
    w = games.filter(pl.col("gsis_id") == "w").row(0, named=True)
    assert (w["pbp_adot"], w["pbp_air_share"], w["pbp_yacoe"]) == (15.0, 1.0, 2.0)
