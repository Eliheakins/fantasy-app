"""Live score, scoreboard and scorecard reads."""

from typing import Any

from fastapi import APIRouter

from fantasy import _view as view
from fantasy import data_api
from fantasy.api_deps import Ctx, DataDir, RequestContext
from fantasy.api_envelope import clean_rows, guarded, rows
from fantasy.api_models import (
    Envelope,
    LiveScoreRow,
    ScoreboardRow,
    ScorecardData,
)
from fantasy.api_routes.common import Week

router = APIRouter()


@router.get("/leagues/{league}/live-score", response_model=Envelope[list[LiveScoreRow]])
def live_score(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.live_score(league, ctx.data_dir, ctx.team)))


def scoreboard_data(league: str, week: int, ctx: RequestContext) -> list[dict[str, Any]]:
    board = data_api.scoreboard(league, week, data_dir=ctx.data_dir, team=ctx.team)
    return clean_rows(view.scoreboard_rows(board))


@router.get("/leagues/{league}/scoreboard", response_model=Envelope[list[ScoreboardRow]])
def scoreboard(league: str, ctx: Ctx, week: Week = 0) -> Any:
    """Every matchup of a week, my (or the viewed) team first. About 0.5 s, so not a job."""
    return guarded(lambda: scoreboard_data(league, week, ctx))


@router.get("/leagues/{league}/scorecard", response_model=Envelope[ScorecardData])
def scorecard(league: str, data_dir: DataDir) -> Any:
    """Archived pre-kickoff projections against actual points. An instant read of parquet."""

    def build() -> dict[str, Any]:
        card = data_api.scorecard(league, data_dir)
        return {
            "rows": rows(card.rows),
            "excluded": card.excluded,
            "weeks_archived": card.weeks_archived,
            "weeks_scored": card.weeks_scored,
            "has_quantiles": card.has_quantiles,
            "sleeper_first_fetch": card.sleeper_first_fetch,
        }

    return guarded(build)
