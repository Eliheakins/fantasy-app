"""
The stat definitions: one declarative file that the app, the model's catalog and the tests share.

`metrics/metrics.json` is the source of truth. A metric's `base_sql` is an aggregate over play rows
with unqualified column names; the query builder adds the table alias. `reference_values` are
figures from an authoritative source, and `tests/test_metric_reference_values.py` checks each
metric's own SQL against them on real data.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nfl_stat.core.config import REPO_ROOT
from nfl_stat.schemas.nlq import MAX_ALIASES, Alias

METRICS_PATH = REPO_ROOT / "metrics" / "metrics.json"

PlayerRole = Literal["passer", "rusher", "receiver"]
PlayType = Literal["pass", "run", "all"]


class Category(BaseModel):
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)


class ReferenceValue(BaseModel):
    gsis_id: str
    player: str
    season: int
    season_type: Literal["REG", "POST"]
    value: float
    tolerance: float = Field(0.0, ge=0.0, le=1.0, description="Allowed relative difference")
    source: str


class MetricDefinition(BaseModel):
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1)
    category: str
    source: Literal["pbp", "league"] = Field(
        "pbp",
        description="'league': points under the picked league's scoring; no play SQL or role",
    )
    player_role: PlayerRole | None = None
    play_type: PlayType | None = None
    base_sql: str = Field(
        "", description="Aggregate over play rows, unqualified columns; empty for a league metric"
    )
    rate_only: bool = Field(..., description="True when the SQL is used as written, never derived")
    better: Literal["higher", "lower"] | None = Field(
        None, description="Which way is better, when one is; unset for neutral stats like ADOT"
    )
    percent_format: bool = False
    play_filter: str | None = Field(
        None,
        min_length=1,
        description="Extra row predicate, e.g. 'sack = 0' for attempt-based stats",
    )
    player_game_column: str | None = Field(
        None,
        min_length=1,
        description="Column of player_game.parquet holding this counting stat's official total",
    )
    team_only: bool = Field(
        False, description="Only a team has this stat (every play, whoever had the ball)"
    )
    family: str | None = Field(
        None,
        min_length=1,
        description="Stats answering one question for different roles; Ask picks the one that fits",
    )
    description: str | None = None
    help: str | None = None
    # Same limits as the catalog sent to the model, so a valid file never makes /nlq/intent 422.
    aliases: list[Alias] = Field(
        default_factory=list, max_length=MAX_ALIASES, description="Lowercase phrases people use"
    )
    reference_values: list[ReferenceValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _source_decides_which_fields_apply(self) -> MetricDefinition:
        if self.source == "league":
            extras = (self.base_sql, self.play_filter, self.player_game_column)
            if any(extras) or self.player_role or self.play_type:
                raise ValueError(f"{self.id!r} is a league metric: no play SQL, role or filter")
        elif not (self.base_sql and self.player_role and self.play_type):
            raise ValueError(f"{self.id!r} needs base_sql, player_role and play_type")
        return self

    @field_validator("aliases")
    @classmethod
    def _aliases_are_lowercase_and_distinct(cls, aliases: list[str]) -> list[str]:
        for alias in aliases:
            if not alias or alias != alias.lower() or alias != alias.strip():
                raise ValueError(f"alias {alias!r} must be non-empty, trimmed and lowercase")
        if any(alias != " ".join(alias.split()) for alias in aliases):
            raise ValueError("aliases use single spaces between words")
        repeated = [a for a, n in Counter(aliases).items() if n > 1]
        if repeated:
            raise ValueError(f"alias {repeated[0]!r} repeats within one metric")
        return aliases


class MetricsFile(BaseModel):
    schema_version: Literal[1]
    categories: list[Category]
    metrics: list[MetricDefinition]

    @model_validator(mode="after")
    def _cross_checks(self) -> MetricsFile:
        ids = Counter(m.id for m in self.metrics)
        duplicate = next((i for i, n in ids.items() if n > 1), None)
        if duplicate:
            raise ValueError(f"Duplicate metric id {duplicate!r}")

        category_ids = Counter(c.id for c in self.categories)
        repeated_category = next((i for i, n in category_ids.items() if n > 1), None)
        if repeated_category:
            raise ValueError(f"Duplicate category id {repeated_category!r}")

        known = set(category_ids)
        for m in self.metrics:
            if m.category not in known:
                raise ValueError(f"Metric {m.id!r} has an undefined category {m.category!r}")

        owner: dict[str, str] = {}
        for m in self.metrics:
            for alias in m.aliases:
                if alias in owner:
                    raise ValueError(
                        f"alias {alias!r} is used by both {owner[alias]!r} and {m.id!r}"
                    )
                owner[alias] = m.id
        return self


def load_metrics(path: Path = METRICS_PATH) -> MetricsFile:
    """Read and validate the metrics file; an invalid file is an error, never a silent default."""
    try:
        return MetricsFile.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError(f"{path.name} is invalid: {e}") from e
