"""The waiver action switches from playoff odds to title odds once the bracket is seeded."""

from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

from fantasy import _actions

PLAYOFF_START = 15


def _adds(playoff_delta: float, title_delta: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "full_name": ["Add"], "drop_name": ["Drop"], "delta_points": [2.0],
            "playoff_delta": [playoff_delta], "title_delta": [title_delta],
        }
    )  # fmt: skip


def _waiver_text(monkeypatch: pytest.MonkeyPatch, week: int, adds: pl.DataFrame) -> list[str]:
    data = SimpleNamespace(current_week=week, playoff_start=PLAYOFF_START)
    monkeypatch.setattr(_actions, "_league", lambda *a, **k: (data, 1))
    monkeypatch.setattr(_actions, "lineup", lambda *a, **k: pl.DataFrame())
    out: Any = _actions.actions("t", odds=pl.DataFrame(), adds=adds)
    return out["text"].to_list()


def test_week_before_playoffs_gates_on_playoff_odds(monkeypatch: pytest.MonkeyPatch) -> None:
    text = _waiver_text(monkeypatch, PLAYOFF_START - 1, _adds(0.02, 0.0))
    assert len(text) == 1 and "+2.0% playoff odds" in text[0]
    assert _waiver_text(monkeypatch, PLAYOFF_START - 1, _adds(0.0, 0.05)) == []


def test_playoff_weeks_gate_on_title_odds(monkeypatch: pytest.MonkeyPatch) -> None:
    text = _waiver_text(monkeypatch, PLAYOFF_START, _adds(0.0, 0.02))
    assert len(text) == 1 and "+2.0% title odds" in text[0]
    assert _waiver_text(monkeypatch, PLAYOFF_START, _adds(0.05, 0.001)) == []
