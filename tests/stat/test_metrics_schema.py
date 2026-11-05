from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nfl_stat.core.config import REPO_ROOT
from nfl_stat.pipeline.nfl_pipeline import NGS_COLS, PART_COLS, PBP_COLS
from nfl_stat.schemas.metrics import METRICS_PATH, MetricsFile, load_metrics

# Columns a metric's SQL may name: the play-by-play columns plus what the build derives.
KNOWN_COLUMNS = set(PBP_COLS) | set(PART_COLS) | set(NGS_COLS) | {"is_red_zone"}
SQL_WORDS = {
    "or",
    "and",
    "sum",
    "avg",
    "count",
    "nullif",
    "cast",
    "as",
    "double",
    "case",
    "when",
    "then",
    "else",
    "end",
}


ATTEMPT_FILTER = "complete_pass = 1 OR incomplete_pass = 1 OR interception = 1"


def _metric(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "pass_yards",
        "label": "Pass yards",
        "category": "passing",
        "player_role": "passer",
        "play_type": "pass",
        "base_sql": "SUM(yards_gained)",
        "rate_only": False,
        "aliases": ["passing yards"],
    }
    return {**base, **overrides}


def _file(*metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "categories": [{"id": "passing", "label": "Passing"}],
        "metrics": list(metrics),
    }


def test_a_valid_file_loads():
    assert MetricsFile.model_validate(_file(_metric())).metrics[0].id == "pass_yards"


def test_duplicate_metric_ids_are_rejected():
    with pytest.raises(ValidationError, match="Duplicate metric id"):
        MetricsFile.model_validate(_file(_metric(), _metric(aliases=["other"])))


def test_a_metric_in_an_undefined_category_is_rejected():
    with pytest.raises(ValidationError, match="category"):
        MetricsFile.model_validate(_file(_metric(category="kicking")))


def test_aliases_must_be_lowercase():
    with pytest.raises(ValidationError, match="lowercase"):
        MetricsFile.model_validate(_file(_metric(aliases=["Passing Yards"])))


def test_an_alias_used_by_two_metrics_is_rejected():
    other = _metric(id="pass_tds", label="Pass TDs", base_sql="SUM(pass_touchdown)")

    with pytest.raises(ValidationError, match="passing yards"):
        MetricsFile.model_validate(_file(_metric(), other | {"aliases": ["passing yards"]}))


def test_an_alias_that_repeats_within_one_metric_is_rejected():
    with pytest.raises(ValidationError, match="repeats"):
        MetricsFile.model_validate(_file(_metric(aliases=["yds", "yds"])))


def test_unknown_roles_and_play_types_are_rejected():
    with pytest.raises(ValidationError):
        MetricsFile.model_validate(_file(_metric(player_role="kicker")))
    with pytest.raises(ValidationError):
        MetricsFile.model_validate(_file(_metric(play_type="punt")))


def test_a_reference_value_needs_a_known_season_type_and_a_sane_tolerance():
    good = {
        "gsis_id": "00-0033873",
        "player": "Patrick Mahomes",
        "season": 2023,
        "season_type": "REG",
        "value": 4183,
        "tolerance": 0.0,
        "source": "nflverse player stats",
    }
    MetricsFile.model_validate(_file(_metric(reference_values=[good])))

    for bad in ({"season_type": "PRE"}, {"tolerance": -0.1}, {"tolerance": 1.5}):
        with pytest.raises(ValidationError):
            MetricsFile.model_validate(_file(_metric(reference_values=[good | bad])))


def test_the_real_file_loads_with_every_stat_the_app_had():
    metrics = load_metrics()

    assert len(metrics.metrics) >= 39
    assert {"pass_yards", "rec_yards", "ypc", "eff_epa"} <= {m.id for m in metrics.metrics}


def test_stats_that_sacks_distort_carry_reference_values_and_the_right_filter():
    by_id = {m.id: m for m in load_metrics().metrics}

    # Sack, penalty and no-play rows are pass rows; official attempt-based totals leave them out.
    # pass_tds shares the filter so its per-play value uses the same denominator as pass yards.
    for stat_id in ("pass_yards", "pass_tds", "cmp_pct", "int_rate"):
        assert by_id[stat_id].play_filter == ATTEMPT_FILTER, stat_id
    # Dropback-based rates count a sack as a play, so they must not filter it out.
    for stat_id in ("pass_sack_rate", "pass_any_a"):
        assert by_id[stat_id].play_filter is None, stat_id
        assert "COUNT(*) + SUM(sack)" not in by_id[stat_id].base_sql, stat_id

    for stat_id in ("pass_yards", "cmp_pct", "int_rate", "pass_sack_rate", "pass_any_a"):
        assert by_id[stat_id].reference_values, f"{stat_id} has no reference value"


def test_empty_text_and_duplicate_categories_are_rejected():
    for field in ("label", "base_sql", "play_filter"):
        with pytest.raises(ValidationError):
            MetricsFile.model_validate(_file(_metric(**{field: ""})))
    duplicated = _file(_metric())
    duplicated["categories"] = [{"id": "passing", "label": "A"}, {"id": "passing", "label": "B"}]
    with pytest.raises(ValidationError, match="Duplicate category"):
        MetricsFile.model_validate(duplicated)


def test_aliases_follow_the_same_limits_the_model_catalog_enforces():
    with pytest.raises(ValidationError):
        MetricsFile.model_validate(_file(_metric(aliases=[f"alias {i}" for i in range(21)])))
    with pytest.raises(ValidationError):
        MetricsFile.model_validate(_file(_metric(aliases=["a" * 61])))
    with pytest.raises(ValidationError, match="single spaces"):
        MetricsFile.model_validate(_file(_metric(aliases=["two  spaces"])))


def test_every_metric_has_at_least_one_alias():
    assert [m.id for m in load_metrics().metrics if not m.aliases] == []


def test_metric_sql_names_only_columns_the_pipeline_builds():
    unknown = {
        m.id: sorted(
            set(
                re.findall(
                    r"\b[a-z_][a-z0-9_]*\b",
                    " ".join(filter(None, [m.base_sql, m.play_filter])).lower(),
                )
            )
            - SQL_WORDS
            - KNOWN_COLUMNS
        )
        for m in load_metrics().metrics
    }

    assert {k: v for k, v in unknown.items() if v} == {}


def test_metric_sql_is_unqualified_because_the_builder_adds_the_table_alias():
    qualified = [m.id for m in load_metrics().metrics if re.search(r"\b(main|sub)\.", m.base_sql)]

    assert qualified == []


def _league_metric(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "league_pts",
        "label": "League points",
        "category": "passing",
        "source": "league",
        "rate_only": False,
        "aliases": ["league points"],
    }
    return {**base, **overrides}


def test_a_league_metric_has_no_play_sql_and_a_play_metric_needs_it():
    loaded = MetricsFile.model_validate(_file(_league_metric())).metrics[0]
    assert loaded.source == "league" and loaded.base_sql == ""

    for bad in (
        {"base_sql": "SUM(yards_gained)"},
        {"play_filter": "sack = 0"},
        {"player_game_column": "passing_yards"},
    ):
        with pytest.raises(ValidationError):
            MetricsFile.model_validate(_file(_league_metric(**bad)))
    with pytest.raises(ValidationError):
        MetricsFile.model_validate(_file(_metric(source="league", base_sql="SUM(yards_gained)")))
    with pytest.raises(ValidationError):
        MetricsFile.model_validate(_file(_metric(source="sleeper")))


def test_the_real_file_has_one_generic_league_metric_and_names_no_league():
    league = [m for m in load_metrics().metrics if m.source == "league"]
    assert [m.id for m in league] == ["league_pts"]
    assert {"fantasy points", "league points", "points in my league"} <= set(league[0].aliases)

    text = METRICS_PATH.read_text(encoding="utf-8").lower()
    catalog = (Path(__file__).parent / "eval" / "catalog.json").read_text(encoding="utf-8").lower()
    leagues = tomllib.loads((REPO_ROOT / "config.toml").read_text())["leagues"]
    names_and_ids = [*leagues, *(cfg["id"] for cfg in leagues.values())]
    for word in [*names_and_ids, "yinz"]:
        assert word.lower() not in text and word.lower() not in catalog, word
