"""Response models for the API, one module per area. `extra="forbid"` makes a drifting data_api
column fail loudly in the smoke tests instead of silently disappearing from the OpenAPI schema.

Every name is importable from here (`from fantasy.api_models import X`), not only from a submodule.
`Envelope` lives in this file on purpose: pydantic puts the defining module in the OpenAPI name of
a generic that collides (`fantasy__api_models__Envelope_Removed___1`), so moving it would rename a
schema."""

from typing import Literal

from fantasy.api_models.base import (
    ApiError,
    Row,
)
from fantasy.api_models.digest import (
    DigestData,
    IdeasInfo,
    LastWeekRow,
    MoveIdeaRow,
    OddsChangeRow,
    ProjectionMissRow,
    WatchRow,
)
from fantasy.api_models.league import (
    KickoffRow,
    LeagueRow,
    RosterRow,
    StatusChangeRow,
    TeamRow,
    UnmatchedData,
    WaiverClearRow,
    WeekCalendarData,
)
from fantasy.api_models.lineup import (
    ActionRow,
    ComparisonRow,
    LineupRow,
    OptionRow,
    ScheduleRow,
    SlotCall,
    StreamerRow,
    StrengthRow,
    SummaryModel,
    SwapNoteModel,
    WinProbabilityData,
)
from fantasy.api_models.players import (
    MarketHistoryRow,
    MarketValueRow,
    OutlookRow,
    OwnerRow,
    OwnersData,
    PlayerPointsRow,
    PlayerProfile,
    PlayerWeekRow,
    RoleWeek,
)
from fantasy.api_models.scores import (
    GameDayData,
    GameDayNow,
    GameDayPoint,
    LiveScoreRow,
    ScoreboardRow,
    ScoreboardSide,
    ScorecardData,
    ScorecardExcluded,
    ScorecardRow,
)
from fantasy.api_models.season import (
    BracketData,
    BracketMatch,
    BracketRound,
    BracketSide,
    LuckRow,
    ManagerGradeRow,
    OddsHistoryRow,
    PowerRankingRow,
    SeasonEventRow,
    SeasonOddsRow,
    SeedRow,
    TeamGradeRow,
    WhatIfRow,
    WinNeedRow,
)
from fantasy.api_models.status import (
    FreshnessRow,
    LiveRefreshData,
    RefreshData,
    RefreshRunRow,
    RefreshStatus,
    StatusData,
)
from fantasy.api_models.trade import (
    MAX_ID_LENGTH,
    MAX_TRADE_IDS,
    AssetRow,
    FoundTradeRow,
    MarketSummary,
    PartnerRow,
    RosterChangeRow,
    TradeEvaluation,
    TradeIds,
    TradeRequest,
    TradeSideRow,
    WaiverRow,
)


class Envelope[T](Row):
    status: Literal["ok", "running", "error"]
    data: T | None
    error: ApiError | None
    started_at: str | None  # set while a job is running


__all__ = [
    "MAX_ID_LENGTH",
    "MAX_TRADE_IDS",
    "ActionRow",
    "ApiError",
    "AssetRow",
    "BracketData",
    "BracketMatch",
    "BracketRound",
    "BracketSide",
    "ComparisonRow",
    "DigestData",
    "Envelope",
    "FoundTradeRow",
    "FreshnessRow",
    "GameDayData",
    "GameDayNow",
    "GameDayPoint",
    "IdeasInfo",
    "KickoffRow",
    "LastWeekRow",
    "LeagueRow",
    "LineupRow",
    "LiveRefreshData",
    "LiveScoreRow",
    "LuckRow",
    "ManagerGradeRow",
    "MarketHistoryRow",
    "MarketSummary",
    "MarketValueRow",
    "MoveIdeaRow",
    "OddsChangeRow",
    "OddsHistoryRow",
    "OptionRow",
    "OutlookRow",
    "OwnerRow",
    "OwnersData",
    "PartnerRow",
    "PlayerPointsRow",
    "PlayerProfile",
    "PlayerWeekRow",
    "PowerRankingRow",
    "ProjectionMissRow",
    "RefreshData",
    "RefreshRunRow",
    "RefreshStatus",
    "RoleWeek",
    "RosterChangeRow",
    "RosterRow",
    "Row",
    "ScheduleRow",
    "ScoreboardRow",
    "ScoreboardSide",
    "ScorecardData",
    "ScorecardExcluded",
    "ScorecardRow",
    "SeasonEventRow",
    "SeasonOddsRow",
    "SeedRow",
    "SlotCall",
    "StatusChangeRow",
    "StatusData",
    "StreamerRow",
    "StrengthRow",
    "SummaryModel",
    "SwapNoteModel",
    "TeamGradeRow",
    "TeamRow",
    "TradeEvaluation",
    "TradeIds",
    "TradeRequest",
    "TradeSideRow",
    "UnmatchedData",
    "WaiverClearRow",
    "WaiverRow",
    "WatchRow",
    "WeekCalendarData",
    "WhatIfRow",
    "WinNeedRow",
    "WinProbabilityData",
]
