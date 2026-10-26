import dataclasses
from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows
from test_simulate_load import LEAGUE, build_store, week_projection

from fantasy import data_api
from fantasy.config import load_config
from fantasy.sim.blend import SLEEPER_WEIGHT, blend_all
from fantasy.stages import simulate as sim


def test_blend_all_is_the_equal_mean_of_the_sources_each_row_has() -> None:
    ours = pl.DataFrame({"gsis_id": ["a", "b", "c"], "week": [7] * 3, "projection": [10.0] * 3})
    sleeper = pl.DataFrame({"gsis_id": ["a", "b"], "week": [7, 7], "other": [14.0, 0.0]})
    props = pl.DataFrame({"gsis_id": ["a", "b"], "week": [7, 7], "other": [12.0, 0.0]})
    out = blend_all(ours, [sleeper, props], "gsis_id", frozenset({"b"}))
    # a: (10 + 14 + 12) / 3; b is Questionable, so every source's 0 counts as missing; c: ours only
    assert out.sort("gsis_id")["projection"].to_list() == pytest.approx([12.0, 10.0, 10.0])


def use_sources(monkeypatch: pytest.MonkeyPatch, sources: tuple[str, ...]) -> None:
    config = dataclasses.replace(load_config(), blend_sources=sources)
    monkeypatch.setattr(sim, "load_config", lambda: config)


def add_outside_tables(tmp_path: Path) -> None:
    """Sleeper 16 for G_QB weeks 3 and 4; FFToday 13 and props 7 for week 3 (current) and a
    stray props row for week 4 that must be ignored."""
    write_rows(
        tmp_path,
        "proj_sleeper",
        [{"league_id": "L1", "sleeper_id": "qb", "week": w, "projection": 16.0} for w in (3, 4)],
    )
    write_rows(
        tmp_path,
        "proj_outside",
        [
            {
                "league_id": "L1",
                "gsis_id": "G_QB",
                "source": "fftoday",
                "season": 2026,
                "week": 3,
                "projection": 13.0,
            }
        ],
    )
    write_rows(
        tmp_path,
        "proj_props",
        [
            {"league_id": "L1", "gsis_id": "G_QB", "season": 2026, "week": w, "projection": 7.0}
            for w in (3, 4)
        ],
    )


@pytest.mark.parametrize(
    ("sources", "week3", "week4"),
    [
        ((), 10.0, 10.0),
        (("sleeper",), (1 - SLEEPER_WEIGHT) * 10.0 + SLEEPER_WEIGHT * 16.0, 13.0),
        (("sleeper", "fftoday", "props"), (10.0 + 16.0 + 13.0 + 7.0) / 4, 13.0),
        (("fftoday", "props"), (10.0 + 13.0 + 7.0) / 3, 10.0),
    ],
)
def test_the_current_week_blends_every_configured_source_and_later_weeks_only_sleeper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sources: tuple[str, ...],
    week3: float,
    week4: float,
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    add_outside_tables(tmp_path)
    use_sources(monkeypatch, sources)
    projections = sim.load_league_data(LEAGUE).projections
    assert week_projection(projections, "G_QB", 3) == week3  # exact: ["sleeper"] is today's blend
    assert week_projection(projections, "G_QB", 4) == week4


def test_missing_layers_lists_a_configured_outside_source_with_no_rows(tmp_path: Path) -> None:
    write_rows(tmp_path, "proj_props")
    missing = data_api.missing_layers(tmp_path)
    assert {"FFToday projections", "prop lines"} <= set(missing)
    write_rows(
        tmp_path,
        "proj_props",
        [{"league_id": "L1", "gsis_id": "g", "season": 2026, "week": 7, "projection": 1.0}],
    )
    assert "prop lines" not in data_api.missing_layers(tmp_path)


def test_config_reads_blend_sources_and_prop_positions(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    body = 'season = 2026\nuser_id = "u"\nn_sims = 10\n{extra}\n[leagues.a]\nid = "1"\n'
    path.write_text(body.format(extra=""))
    default = load_config(path)
    assert (default.blend_sources, default.prop_positions) == (("sleeper",), ("RB", "WR"))
    path.write_text(
        body.format(extra='blend_sources = ["sleeper", "props"]\nprop_positions = ["WR"]')
    )
    assert load_config(path).blend_sources == ("sleeper", "props")
    assert load_config(path).prop_positions == ("WR",)
    path.write_text(body.format(extra='blend_sources = ["espn"]'))
    with pytest.raises(ValueError, match="blend_sources"):
        load_config(path)
    path.write_text(body.format(extra='prop_positions = ["K"]'))
    with pytest.raises(ValueError, match="prop_positions"):
        load_config(path)
