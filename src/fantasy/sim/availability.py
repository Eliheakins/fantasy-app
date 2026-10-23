"""Scale projections by the chance a player suits up, from Sleeper's injury status.

Rates come from nflverse 2018 to 2025 reports: among skill players with at least 5 touches or
targets the week before, 0.2% of Out, 1.8% of Doubtful and 73% of Questionable players had any
touch or target, against 96% of players with no designation. Questionable is therefore 0.76.
Long-term designations sit out the 4-game minimum; after that the player is assumed back.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

STATUS_RATE = {"Out": 0.0, "Doubtful": 0.02, "Questionable": 0.76}
LONG_TERM = frozenset({"IR", "PUP", "NFI", "Sus", "DNR"})
LONG_TERM_WEEKS = 4
EASTERN = ZoneInfo("America/New_York")


def rate(status: str | None, week: int, current_week: int) -> float:
    if status in LONG_TERM:
        return 0.0 if week < current_week + LONG_TERM_WEEKS else 1.0
    if week == current_week:
        return STATUS_RATE.get(status or "", 1.0)
    return 1.0  # shortcut: a game-day status says nothing about later weeks


def scale_projections(
    projections: pl.DataFrame, status: dict[str, str], current_week: int
) -> pl.DataFrame:
    """Return `projections` with `projection` multiplied by each player's availability and a
    `play_prob` column holding that availability (the chance he plays)."""
    factors = pl.Series(
        [
            rate(status.get(g), w, current_week)
            for g, w in zip(projections["gsis_id"], projections["week"], strict=True)
        ],
        dtype=pl.Float64,
    )
    return projections.with_columns(
        (pl.col("projection") * factors).alias("projection"), factors.alias("play_prob")
    )


GAME_MINUTES = (
    200  # shortcut: overtime and delays read as final early; upgrade with a live game clock
)


def kickoffs(schedules: pl.DataFrame, season: int, week: int) -> dict[str, datetime]:
    """Kickoff time of each team's game this week. Schedule times are US Eastern."""
    games = schedules.filter((pl.col("season") == season) & (pl.col("week") == week))
    out: dict[str, datetime] = {}
    for day, time, away, home in games.select(
        "gameday", "gametime", "away_team", "home_team"
    ).iter_rows():
        if day is None or time is None:
            continue
        kickoff = datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=EASTERN)
        out[away] = out[home] = kickoff
    return out


def remaining_share(kickoff: datetime | None, now: datetime) -> float:
    """Share of a game still to play: 1 before kickoff, 0 once GAME_MINUTES have passed."""
    if kickoff is None or now <= kickoff:
        return 1.0
    elapsed = (now - kickoff).total_seconds() / 60
    return max(0.0, 1.0 - elapsed / GAME_MINUTES)


def locked_teams(schedules: pl.DataFrame, season: int, week: int, now: datetime) -> set[str]:
    """NFL teams whose game has kicked off."""
    return {t for t, k in kickoffs(schedules, season, week).items() if k <= now}
