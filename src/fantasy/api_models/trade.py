"""Trade, waiver and market-summary models."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from fantasy.api_models.base import Row


class PartnerRow(Row):
    roster_id: int
    team_name: str


class AssetRow(Row):
    gsis_id: str
    full_name: str
    position: str
    ros_points: float
    label: str


class WaiverRow(Row):
    gsis_id: str
    full_name: str
    position: str
    drop_name: str
    delta_points: float
    playoff_delta: float | None
    title_delta: float | None
    se_title: float | None
    trending_adds: int | None


class TradeSideRow(Row):
    side: str
    roster_id: int
    team_name: str
    playoff_before: float
    playoff_after: float
    title_before: float
    title_after: float
    wins_before: float
    wins_after: float


class RosterChangeRow(Row):
    team_name: str
    action: str
    full_name: str
    position: str


class MarketSummary(Row):
    """Market value each side gives and gets (FantasyCalc), the hint and the values' date."""

    give_value: float
    get_value: float
    hint: str
    fetched_at: str
    accepted_share: float | None = None  # share of past accepted trades this lopsided or worse
    accepted_sides: int = 0  # past accepting sides the share is out of


class TradeEvaluation(Row):
    odds: list[TradeSideRow]
    roster_changes: list[RosterChangeRow]
    warning: str | None
    trade_deadline: int | None
    market: MarketSummary | None


class FoundTradeRow(Row):
    partner: str
    give: str
    get: str
    give_ids: list[str]
    get_ids: list[str]
    kind: Literal["win-win", "need swap"]
    my_fills: str
    their_fills: str
    my_fit: float
    their_fit: float
    market: MarketSummary | None
    my_playoff: float
    my_title: float
    their_playoff: float
    their_title: float
    se_title: float


MAX_TRADE_IDS, MAX_ID_LENGTH = 10, 64


TradeIds = Annotated[
    list[Annotated[str, Field(max_length=MAX_ID_LENGTH)]],
    Field(min_length=1, max_length=MAX_TRADE_IDS),
]


class TradeRequest(BaseModel):
    partner_roster_id: int
    give_ids: TradeIds
    get_ids: TradeIds
