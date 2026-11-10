from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Granularity = Literal["total", "per_game", "per_play"]

# Matches MAX_SELECTED_STATS in the frontend query-builder store.
MAX_INTENT_STATS = 5


# The client sends the catalog with each ask and it goes into a paid model call, so bound it
# at 1.5x what the app sends (2026-11-10: 76 stats, 42 filters, 7 aliases of 35 characters at
# most, text up to 29 characters, 13.0 KB serialized). Refresh the measure with
# tests/stat/eval/catalog.json when the catalog grows.
MAX_CATALOG_STATS = 114
MAX_CATALOG_FILTERS = 63
MAX_ALIASES = 11
MAX_INTENT_BODY_BYTES = 20_000

ShortText = Annotated[str, Field(max_length=44)]
Alias = Annotated[str, Field(max_length=52)]


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
    ranking: bool = Field(
        False, description="The question asks who leads or ranks first; the client orders the rows"
    )


class QueryOutcome(BaseModel):
    outcome: Literal["query"] = "query"
    intent: QueryIntent


class UnsupportedOutcome(BaseModel):
    """No stat or filter can answer the question; `reason` is shown to the user."""

    outcome: Literal["unsupported"] = "unsupported"
    reason: str = Field(..., min_length=1, max_length=300)


IntentOutcome = Annotated[QueryOutcome | UnsupportedOutcome, Field(discriminator="outcome")]
