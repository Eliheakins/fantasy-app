"""A league someone added that the app cannot handle is skipped, marked and reported; the same
failure in a config.toml league still stops the run."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from test_score import SCHEDULE, stat_row

from fantasy import _runs
from fantasy.auth import accounts, leagues
from fantasy.config import load_config
from fantasy.sim.lineup import UnknownSlot
from fantasy.stages import score as score_stage
from fantasy.stages import simulate as sim_stage

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
CONFIG_ID = next(iter(load_config().leagues.values()))
ADDED_ID = "999111"
GOOD_SCORING = {"rec": 1.0}
BONUS_SCORING = {"rec": 1.0, "bonus_rec_te": 0.5}  # a key the app does not map


def league_row(league_id: str, scoring: dict[str, float]) -> dict[str, Any]:
    return {
        "league_id": league_id,
        "league_key": f"key-{league_id}",
        "scoring_settings": json.dumps(scoring),
        "num_teams": 10,
        "playoff_teams": 6,
        "playoff_week_start": 15,
    }


@pytest.fixture(autouse=True)
def clean_soft_failures() -> Iterator[None]:
    _runs._soft_failures.clear()
    yield
    _runs._soft_failures.clear()


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    """An accounts file holding the added league as a registered, queued league."""
    with accounts.open_db(tmp_path) as conn:
        token = accounts.create_invite(conn, "a@example.com", NOW)
        account = accounts.redeem_invite(conn, token, "a long enough password", NOW)
        leagues.add(conn, int(account["id"]), ADDED_ID, "Added", NOW)
    return tmp_path


def registry_state(data_dir: Path) -> tuple[str, str | None]:
    with accounts.open_db(data_dir) as conn:
        [row] = leagues.registered(conn)
    return row["status"], row["error"]


def patch_tables(
    monkeypatch: pytest.MonkeyPatch, module: Any, tables: dict[str, pl.DataFrame]
) -> dict[str, pl.DataFrame]:
    written: dict[str, pl.DataFrame] = {}
    monkeypatch.setattr(module.store, "read_table", lambda name, *a, **k: tables[name])
    monkeypatch.setattr(module.store, "write_tables", lambda t, **k: written.update(t))
    return written


def score_tables(rows: list[dict[str, Any]]) -> dict[str, pl.DataFrame]:
    stats = stat_row(player_id="00-1", position="WR", team="KC", season=2026, week=7)
    return {"leagues": pl.DataFrame(rows), "nfl_schedules": SCHEDULE, "nfl_player_stats": stats}


def test_score_skips_an_added_league_with_unmapped_scoring_and_scores_the_rest(
    monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    rows = [league_row(CONFIG_ID, GOOD_SCORING), league_row(ADDED_ID, BONUS_SCORING)]
    written = patch_tables(monkeypatch, score_stage, score_tables(rows))

    score_stage.run(data_dir=registry)

    assert set(written["player_points"]["league_id"]) == {CONFIG_ID}
    status, error = registry_state(registry)
    assert status == "error" and "bonus_rec_te" in str(error)
    assert any(f"key-{ADDED_ID}" in note for note in _runs._soft_failures)


def test_score_still_stops_for_a_config_league_with_unmapped_scoring(
    monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    patch_tables(monkeypatch, score_stage, score_tables([league_row(CONFIG_ID, BONUS_SCORING)]))

    with pytest.raises(ValueError, match="bonus_rec_te"):
        score_stage.run(data_dir=registry)

    assert _runs._soft_failures == []
    assert registry_state(registry)[0] == "queued"  # nothing was marked


def simulate_with(
    monkeypatch: pytest.MonkeyPatch, registry: Path, rows: list[dict[str, Any]]
) -> list[bool]:
    """Run simulate over `rows` where every league load fails on an unknown slot; returns the
    `strict` flag each load was given."""
    strict_seen: list[bool] = []

    def load(league: dict[str, Any], strict: bool = True, data_dir: Path | None = None) -> None:
        strict_seen.append(strict)
        raise UnknownSlot("unknown roster slot 'WRRB_FLEX'")

    patch_tables(monkeypatch, sim_stage, {"leagues": pl.DataFrame(rows)})
    monkeypatch.setattr(sim_stage, "load_league_data", load)
    sim_stage.run(archive=False, data_dir=registry)
    return strict_seen


def test_simulate_skips_an_added_league_with_an_unknown_slot_without_strict_loading(
    monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    strict_seen = simulate_with(monkeypatch, registry, [league_row(ADDED_ID, GOOD_SCORING)])

    assert strict_seen == [False]  # an added league's unprojected players only warn
    status, error = registry_state(registry)
    assert status == "error" and "WRRB_FLEX" in str(error)
    assert any(f"key-{ADDED_ID}" in note and "WRRB_FLEX" in note for note in _runs._soft_failures)


def test_simulate_skips_an_added_league_with_unmapped_scoring_before_loading_it(
    monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    strict_seen = simulate_with(monkeypatch, registry, [league_row(ADDED_ID, BONUS_SCORING)])

    assert strict_seen == []
    assert "bonus_rec_te" in str(registry_state(registry)[1])


def test_simulate_still_stops_for_a_config_league_that_fails(
    monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    with pytest.raises(UnknownSlot):
        simulate_with(monkeypatch, registry, [league_row(CONFIG_ID, GOOD_SCORING)])

    assert _runs._soft_failures == []
    assert registry_state(registry)[0] == "queued"
