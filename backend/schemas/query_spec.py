"""
The typed query the app executes, whatever produced it (the model, a rules parser, a saved URL).

The frontend mirrors this in `frontend/src/shared/lib/schemas/querySpec.ts` with the same rules.
Every shape here validates; the engine reports which ones it cannot run yet.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from schemas.nlq import Granularity

MAX_SPEC_METRICS = 5
MAX_SPEC_LIMIT = 100


class PlayersSubject(BaseModel):
    kind: Literal["players"]
    gsis_ids: list[str] = Field(..., min_length=1)


class TeamsSubject(BaseModel):
    kind: Literal["teams"]
    teams: list[str] = Field(..., min_length=1)


class LeagueSubject(BaseModel):
    kind: Literal["league"]


Subject = Annotated[PlayersSubject | TeamsSubject | LeagueSubject, Field(discriminator="kind")]


class OrderBy(BaseModel):
    metric: str
    direction: Literal["asc", "desc"] = "desc"


class QuerySpec(BaseModel):
    subject: Subject
    metrics: list[str] = Field(..., min_length=1, max_length=MAX_SPEC_METRICS)
    filters: list[str] = Field(default_factory=list)
    granularity: Granularity = "total"
    group_by: list[Literal["season", "week"]] = Field(default_factory=list)
    order_by: OrderBy | None = None
    limit: int | None = Field(None, ge=1, le=MAX_SPEC_LIMIT)

    @model_validator(mode="after")
    def _cross_checks(self) -> QuerySpec:
        if len(set(self.metrics)) != len(self.metrics):
            raise ValueError("metrics repeat")
        if self.order_by and self.order_by.metric not in self.metrics:
            raise ValueError("order_by must name one of the metrics")
        if self.subject.kind == "league" and (self.order_by is None or self.limit is None):
            raise ValueError("a league query needs order_by and limit")
        return self
