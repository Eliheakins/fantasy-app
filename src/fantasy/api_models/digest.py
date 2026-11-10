"""The weekly digest models."""

from typing import Literal

from fantasy.api_models.base import Row


class LastWeekRow(Row):
    week: int
    roster_id: int
    team_name: str
    opponent: str | None
    points: float
    opp_points: float
    result: Literal["W", "L", "T"]
    bench_points_left: float | None  # null: unknown (playoff week, no player rows), not zero
    luck: float | None  # wins above what the all-play record predicts, that week only


class ProjectionMissRow(Row):
    gsis_id: str
    full_name: str | None
    position: str
    points: float | None
    projection: float | None  # null where proj_snapshots has no row for the player
    diff: float | None


class OddsChangeRow(Row):
    roster_id: int
    team_name: str
    is_me: bool
    as_of_week: int
    prev_as_of_week: int | None
    p_playoffs: float | None
    p_title: float | None
    d_playoffs: float | None  # null without an earlier week, never zero
    d_title: float | None


class MoveIdeaRow(Row):
    kind: Literal["waiver", "trade"]
    partner: str | None
    give: str
    get: str
    give_ids: list[str]
    get_ids: list[str]
    rank: int
    playoff_delta: float | None
    title_delta: float | None
    se_title: float | None
    delta_points: float | None


class IdeasInfo(Row):
    is_mine: bool  # ideas are stored for my team only; false means the lists are empty by design
    created_at: str | None  # when the digest stage ran
    as_of_week: int | None
    current_week: int | None
    trade_deadline: int | None
    deadline_passed: bool


class WatchRow(Row):
    gsis_id: str
    full_name: str
    position: str
    ros_points: float
    reasons: list[str]


class DigestData(Row):
    last_week: LastWeekRow | None  # null in week 1
    performance: list[ProjectionMissRow]
    watch: list[WatchRow]
    odds_change: list[OddsChangeRow]
    waivers: list[MoveIdeaRow]
    trades: list[MoveIdeaRow]
    ideas: IdeasInfo
