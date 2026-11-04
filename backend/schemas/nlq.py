from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Granularity = Literal["total", "per_game", "per_play"]

# Matches MAX_SELECTED_STATS in the frontend query-builder store.
MAX_INTENT_STATS = 5


class CatalogStat(BaseModel):
    id: str
    label: str
    category: str
    aliases: list[str] = Field(default_factory=list, description="Other phrases for this stat")


class CatalogFilter(BaseModel):
    id: str
    label: str
    group: str


class IntentRequest(BaseModel):
    """The frontend owns the stat and filter catalog, so it sends the allowed ids with each ask."""

    question: str = Field(..., min_length=1, max_length=2000)
    stats: list[CatalogStat] = Field(..., min_length=1)
    filters: list[CatalogFilter] = Field(default_factory=list)


class QueryIntent(BaseModel):
    stat_ids: list[str] = Field(..., min_length=1)
    filter_ids: list[str] = Field(default_factory=list)
    granularity: Granularity = "total"


class QueryOutcome(BaseModel):
    outcome: Literal["query"] = "query"
    intent: QueryIntent


class UnsupportedOutcome(BaseModel):
    """No stat or filter can answer the question; `reason` is shown to the user."""

    outcome: Literal["unsupported"] = "unsupported"
    reason: str = Field(..., min_length=1, max_length=300)


IntentOutcome = Annotated[QueryOutcome | UnsupportedOutcome, Field(discriminator="outcome")]
