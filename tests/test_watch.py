from pathlib import Path

import pytest
from test_data_api_characterization import _engine_store
from test_lineup_live import _with

from fantasy import data_api
from fantasy.sim.watch import ROLE_WINDOW, market_drop, role_drop


def test_role_drop_needs_enough_games_and_a_big_enough_fall() -> None:
    steady = [0.7, 0.7, 0.7, 0.7, 0.7]
    fell = [0.8, 0.8, 0.5, 0.5, 0.5]
    assert role_drop(steady) is None
    assert role_drop(fell[:-1]) is None  # 2 prior games are needed besides the last 3
    assert role_drop([0.8, 0.8, 0.5, 0.5, 0.5]) == pytest.approx((0.8, 0.5))
    assert role_drop([0.8, 0.8, 0.66, 0.66, 0.66]) is None  # a 14-point fall is under 15


def test_role_drop_compares_the_recent_window_with_the_window_before_it() -> None:
    older = [0.2] * 5  # games long before the prior window do not count
    games = [*older, 0.8, 0.8, 0.8, 0.5, 0.5, 0.5]
    assert ROLE_WINDOW == 3
    assert role_drop(games) == pytest.approx((0.8, 0.5))


def test_market_drop_is_a_share_of_the_value_then_and_ignores_cheap_players() -> None:
    assert market_drop(800.0, -200.0) == pytest.approx(0.2)  # 1,000 then, 800 now
    assert market_drop(900.0, -100.0) is None  # 10%
    assert market_drop(300.0, -300.0) is None  # under the value floor
    assert market_drop(2000.0, 300.0) is None  # rising


def test_market_drop_ignores_a_player_without_a_value_or_a_trend() -> None:
    assert market_drop(None, -300.0) is None
    assert market_drop(800.0, None) is None


def test_the_watchlist_lists_a_flagged_starter_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _with(monkeypatch, injuries={"G_WR": ("Questionable", "Hamstring", None)})

    out = data_api.watchlist("t", tmp_path)

    reasons = dict(zip(out["gsis_id"], out["reasons"], strict=True))
    assert reasons["G_WR"][0].startswith("Questionable")
