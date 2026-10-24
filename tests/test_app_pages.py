from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows
from streamlit.testing.v1 import AppTest
from test_simulate_load import build_store

from fantasy import data_api

APP = Path(__file__).parent.parent / "app"
PAGES = APP / "pages"
TIMEOUT = 60


def _trades(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.syspath_prepend(str(APP))  # pages import `ui` as a sibling module
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    write_rows(tmp_path, "trending")
    # `leagues` binds the real data dir as a default argument, so point it at the test league
    only = pl.DataFrame({"league_key": ["t"], "name": ["Test"], "current_week": [2]})
    monkeypatch.setattr(data_api, "leagues", lambda *args, **kwargs: only)
    return AppTest.from_file(str(PAGES / "Trades.py"), default_timeout=TIMEOUT)


def test_trade_result_stays_after_another_widget_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _trades(tmp_path, monkeypatch).run()
    assert not app.exception
    app.multiselect(key="give_t").set_value(["G_RB"])
    app.multiselect(key="get_t_2").set_value(["G_OPP"])
    app.run()
    next(b for b in app.button if b.label == "Evaluate").click().run()
    assert len(app.metric) == 6  # three metrics for each side
    league = app.sidebar.radio[0]
    league.set_value(league.value).run()  # a widget rerun that does not press the button
    assert len(app.metric) == 6
    assert not app.exception
