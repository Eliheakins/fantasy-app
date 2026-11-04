from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from schemas.query_spec import MAX_SPEC_METRICS, QuerySpec


def _spec(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "subject": {"kind": "players", "gsis_ids": ["00-0033873"]},
        "metrics": ["pass_yards"],
        "filters": ["season-2023"],
        "granularity": "total",
    }
    return {**base, **overrides}


def test_a_player_spec_loads_with_defaults_for_the_optional_parts():
    spec = QuerySpec.model_validate(_spec())

    assert spec.group_by == []
    assert spec.order_by is None
    assert spec.limit is None


def test_a_league_leaderboard_spec_loads():
    spec = QuerySpec.model_validate(
        _spec(
            subject={"kind": "league"},
            order_by={"metric": "pass_yards", "direction": "desc"},
            limit=10,
        )
    )

    assert spec.subject.kind == "league"
    assert spec.limit == 10


def test_a_league_spec_needs_an_order_and_a_limit():
    with pytest.raises(ValidationError, match="league"):
        QuerySpec.model_validate(_spec(subject={"kind": "league"}))


def test_order_by_must_name_one_of_the_metrics():
    with pytest.raises(ValidationError, match="order_by"):
        QuerySpec.model_validate(_spec(order_by={"metric": "rec_yards", "direction": "desc"}))


def test_limit_is_capped_and_positive():
    for bad in (0, 101):
        with pytest.raises(ValidationError):
            QuerySpec.model_validate(_spec(limit=bad))


def test_metrics_are_required_unique_and_capped():
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(metrics=[]))
    with pytest.raises(ValidationError, match="repeat"):
        QuerySpec.model_validate(_spec(metrics=["pass_yards", "pass_yards"]))
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(metrics=[f"m{i}" for i in range(MAX_SPEC_METRICS + 1)]))


def test_a_players_subject_needs_at_least_one_player():
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(subject={"kind": "players", "gsis_ids": []}))


def test_a_teams_subject_needs_at_least_one_team():
    QuerySpec.model_validate(_spec(subject={"kind": "teams", "teams": ["KC"]}))
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(subject={"kind": "teams", "teams": []}))


def test_unknown_subject_kinds_and_group_by_values_are_rejected():
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(subject={"kind": "coaches"}))
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(group_by=["decade"]))


def test_values_that_the_typescript_schema_rejects_are_rejected_here_too():
    for limit in (True, "5", 5.0):
        with pytest.raises(ValidationError):
            QuerySpec.model_validate(_spec(limit=limit))
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(metrics=[""]))
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(subject={"kind": "players", "gsis_ids": [""]}))


def test_repeated_players_filters_and_group_by_are_rejected():
    with pytest.raises(ValidationError, match="repeat"):
        QuerySpec.model_validate(_spec(subject={"kind": "players", "gsis_ids": ["a", "a"]}))
    with pytest.raises(ValidationError, match="repeat"):
        QuerySpec.model_validate(_spec(filters=["season-2023", "season-2023"]))
    with pytest.raises(ValidationError, match="repeat"):
        QuerySpec.model_validate(_spec(group_by=["season", "season"]))


def test_list_sizes_are_bounded():
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(_spec(filters=[f"f{i}" for i in range(51)]))
