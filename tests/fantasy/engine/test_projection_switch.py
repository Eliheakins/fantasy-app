from pathlib import Path

import pytest
from store_fixture import write_rows

from fantasy import store
from fantasy.config import Config, load_config


def projection_row(season: int, week: int, is_future: bool, value: float) -> dict:
    return {
        "league_id": "L",
        "gsis_id": "A",
        "position": "WR",
        "team": "KC",
        "season": season,
        "week": week,
        "projection": value,
        "context": 1.0,
        "has_history": True,
        "is_future": is_future,
    }


def configured(monkeypatch: pytest.MonkeyPatch, model: str) -> None:
    config = load_config()
    changed = Config(**{**config.__dict__, "projection_model": model})
    monkeypatch.setattr("fantasy.store.load_config", lambda: changed)


def test_the_baseline_is_used_when_the_learned_table_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_rows(tmp_path, "proj_baseline", [projection_row(2025, 1, False, 10.0)])
    configured(monkeypatch, "learned")
    assert store.projection_name(tmp_path) == "proj_baseline"


def test_the_learned_table_is_used_when_configured_and_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_rows(tmp_path, "proj_baseline", [projection_row(2025, 1, False, 10.0)])
    write_rows(tmp_path, "proj_learned", [projection_row(2025, 1, False, 12.0)])
    configured(monkeypatch, "learned")
    assert store.projection_name(tmp_path) == "proj_learned"
    assert store.projection_table(tmp_path)["projection"].to_list() == [12.0]
    configured(monkeypatch, "baseline")
    assert store.projection_name(tmp_path) == "proj_baseline"
    assert store.projection_table(tmp_path)["projection"].to_list() == [10.0]


def test_early_learned_history_is_left_out_because_those_models_saw_later_seasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        projection_row(2019, 3, False, 1.0),
        projection_row(2020, 3, False, 2.0),
        projection_row(2021, 3, False, 3.0),
        projection_row(2019, 3, True, 4.0),  # a future row is never dropped
    ]
    write_rows(tmp_path, "proj_learned", rows)
    configured(monkeypatch, "learned")
    out = store.projection_table(tmp_path)
    assert sorted(out["projection"].to_list()) == [3.0, 4.0]


def test_config_defaults_to_the_baseline_and_rejects_an_unknown_model(tmp_path: Path) -> None:
    text = (Path(__file__).resolve().parents[3] / "config.toml").read_text()
    lines = [x for x in text.splitlines() if "projection_model" not in x]
    without = tmp_path / "a.toml"
    without.write_text("\n".join(lines) + "\n")
    assert load_config(without).projection_model == "baseline"
    bad = tmp_path / "b.toml"
    bad.write_text('projection_model = "magic"\n' + without.read_text())
    with pytest.raises(ValueError, match="projection_model"):
        load_config(bad)


def test_the_shipped_config_uses_the_learned_model() -> None:
    assert load_config().projection_model == "learned"


def test_size_calibration_is_skipped_for_the_learned_projection_and_kept_for_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polars as pl

    from fantasy.sim.calibration import calibrated

    write_rows(tmp_path, "proj_baseline", [projection_row(2025, 1, False, 10.0)])
    write_rows(tmp_path, "proj_learned", [projection_row(2025, 1, False, 10.0)])
    curve = {"league_id": "L", "position": "WR", "center": 10.0, "factor": 0.5, "n": 100}
    write_rows(tmp_path, "projection_calibration", [curve])
    frame = pl.DataFrame({"league_id": ["L"], "position": ["WR"], "projection": [10.0]})
    configured(monkeypatch, "learned")
    assert calibrated(frame, tmp_path)["projection"].to_list() == [
        10.0
    ]  # the learned model is calibrated
    configured(monkeypatch, "baseline")
    assert calibrated(frame, tmp_path)["projection"].to_list() == [
        5.0
    ]  # the baseline over-projects


@pytest.mark.parametrize(
    "key, value",
    [
        ("stat_line_model", '"false"'),
        ("n_sims", "0"),
        ("n_sims", "true"),
    ],
)
def test_config_rejects_a_text_switch_and_a_non_positive_simulation_count(
    tmp_path: Path, key: str, value: str
) -> None:
    text = (Path(__file__).resolve().parents[3] / "config.toml").read_text()
    kept = [x for x in text.splitlines() if not x.startswith(key)]
    bad = tmp_path / "bad.toml"
    bad.write_text(f"{key} = {value}\n" + "\n".join(kept) + "\n")
    with pytest.raises(ValueError, match=key):
        load_config(bad)
