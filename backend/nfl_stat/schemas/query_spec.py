"""
The typed query the app executes, whatever produced it (the model, a rules parser, a saved URL).

The frontend mirrors this in `frontend/src/shared/lib/schemas/querySpec.ts` with the same rules.
Every shape here validates; the engine reports which ones it cannot run yet.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

from nfl_stat.schemas.nlq import Granularity

MAX_SPEC_METRICS = 5
MAX_SPEC_LIMIT = 100
MAX_SPEC_FILTERS = 50
MAX_SPEC_SUBJECTS = 50

NonEmpty = Annotated[str, Field(min_length=1)]


class PlayersSubject(BaseModel):
    kind: Literal["players"]
    gsis_ids: list[NonEmpty] = Field(..., min_length=1, max_length=MAX_SPEC_SUBJECTS)


class TeamsSubject(BaseModel):
    kind: Literal["teams"]
    teams: list[NonEmpty] = Field(..., min_length=1, max_length=MAX_SPEC_SUBJECTS)


class LeagueSubject(BaseModel):
    kind: Literal["league"]


Subject = Annotated[PlayersSubject | TeamsSubject | LeagueSubject, Field(discriminator="kind")]


class OrderBy(BaseModel):
    metric: NonEmpty
    direction: Literal["asc", "desc"] = "desc"


class QuerySpec(BaseModel):
    subject: Subject
    metrics: list[NonEmpty] = Field(..., min_length=1, max_length=MAX_SPEC_METRICS)
    filters: list[NonEmpty] = Field(default_factory=list, max_length=MAX_SPEC_FILTERS)
    granularity: Granularity = "total"
    group_by: list[Literal["season", "week"]] = Field(default_factory=list, max_length=2)
    order_by: OrderBy | None = None
    limit: StrictInt | None = Field(None, ge=1, le=MAX_SPEC_LIMIT)

    @model_validator(mode="after")
    def _cross_checks(self) -> QuerySpec:
        people = (
            self.subject.gsis_ids
            if self.subject.kind == "players"
            else self.subject.teams
            if self.subject.kind == "teams"
            else []
        )
        for name, values in (
            ("metrics", self.metrics),
            ("filters", self.filters),
            ("group_by", self.group_by),
            ("subject", people),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} repeat")
        if self.order_by and self.order_by.metric not in self.metrics:
            raise ValueError("order_by must name one of the metrics")
        if self.subject.kind == "league" and (self.order_by is None or self.limit is None):
            raise ValueError("a league query needs order_by and limit")
        return self
