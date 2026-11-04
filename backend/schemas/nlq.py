from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Granularity = Literal["total", "per_game", "per_play"]

# Matches MAX_SELECTED_STATS in the frontend query-builder store.
MAX_INTENT_STATS = 5


# The client sends the catalog with each ask and it goes into the prompt, so bound its size.
MAX_CATALOG_STATS = 200
MAX_CATALOG_FILTERS = 400
MAX_ALIASES = 20

ShortText = Annotated[str, Field(max_length=100)]
Alias = Annotated[str, Field(max_length=60)]


class CatalogStat(BaseModel):
    id: ShortText
    label: ShortText
    category: ShortText
    aliases: list[Alias] = Field(
        default_factory=list, max_length=MAX_ALIASES, description="Other phrases for this stat"
    )


class CatalogFilter(BaseModel):
    id: ShortText
    label: ShortText
    group: ShortText


class IntentRequest(BaseModel):
    """The frontend owns the stat and filter catalog, so it sends the allowed ids with each ask."""

    question: str = Field(..., min_length=1, max_length=2000)
    stats: list[CatalogStat] = Field(..., min_length=1, max_length=MAX_CATALOG_STATS)
    filters: list[CatalogFilter] = Field(default_factory=list, max_length=MAX_CATALOG_FILTERS)


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
