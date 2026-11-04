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

METRICS_PATH = Path(__file__).resolve().parents[2] / "metrics" / "metrics.json"

PlayerRole = Literal["passer", "rusher", "receiver"]
PlayType = Literal["pass", "run", "all"]


class Category(BaseModel):
    id: str
    label: str


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
    label: str
    category: str
    player_role: PlayerRole
    play_type: PlayType
    base_sql: str = Field(..., description="Aggregate over play rows; columns are unqualified")
    rate_only: bool = Field(..., description="True when the SQL is used as written, never derived")
    percent_format: bool = False
    play_filter: str | None = Field(
        None, description="Extra row predicate, e.g. 'sack = 0' for attempt-based stats"
    )
    description: str | None = None
    help: str | None = None
    aliases: list[str] = Field(default_factory=list, description="Lowercase phrases people use")
    reference_values: list[ReferenceValue] = Field(default_factory=list)

    @field_validator("aliases")
    @classmethod
    def _aliases_are_lowercase_and_distinct(cls, aliases: list[str]) -> list[str]:
        for alias in aliases:
            if not alias or alias != alias.lower() or alias != alias.strip():
                raise ValueError(f"alias {alias!r} must be non-empty, trimmed and lowercase")
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

        known = {c.id for c in self.categories}
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
