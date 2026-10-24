"""Scale projections by the chance a player suits up, from Sleeper's injury status.

Rates come from nflverse 2018 to 2025 reports: among skill players with at least 5 touches or
targets the week before, 0.2% of Out, 1.8% of Doubtful and 73% of Questionable players had any
touch or target, against 96% of players with no designation. Questionable is therefore 0.76.
Long-term designations sit out the 4-game minimum; after that the player is assumed back.
"""

import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

STATUS_RATE = {"Out": 0.0, "Doubtful": 0.02, "Questionable": 0.76}
LONG_TERM = frozenset({"IR", "PUP", "NFI", "Sus", "DNR"})
LONG_TERM_WEEKS = 4
HEALTHY_STATUSES = frozenset({"", "NA", "Probable"})  # no designation, or one that plays
EASTERN = ZoneInfo("America/New_York")


def rate(status: str | None, week: int, current_week: int) -> float:
    if status and status not in STATUS_RATE and status not in LONG_TERM | HEALTHY_STATUSES:
        warnings.warn(
            f"unrecognised injury status {status!r}, treated as Questionable", stacklevel=2
        )
        status = "Questionable"
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


def _games(schedules: pl.DataFrame, season: int, week: int) -> list[tuple]:
    games = schedules.filter((pl.col("season") == season) & (pl.col("week") == week))
    return list(games.select("gameday", "gametime", "away_team", "home_team").iter_rows())


def missing_kickoffs(schedules: pl.DataFrame, season: int, week: int) -> set[str]:
    """Teams that have a game this week but no kickoff time on the schedule. For these a caller
    cannot tell an unplayed game from a finished one, so it must not default to "not started"."""
    return {
        t
        for day, time, away, home in _games(schedules, season, week)
        if day is None or time is None
        for t in (away, home)
    }


def kickoffs(schedules: pl.DataFrame, season: int, week: int) -> dict[str, datetime]:
    """Kickoff time of each team's game this week. Schedule times are US Eastern. Warns about
    teams with a game but no kickoff time (they are left out; see `missing_kickoffs`)."""
    out: dict[str, datetime] = {}
    for day, time, away, home in _games(schedules, season, week):
        if day is None or time is None:
            continue
        kickoff = datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=EASTERN)
        out[away] = out[home] = kickoff
    missing = missing_kickoffs(schedules, season, week) - set(out)
    if missing:
        warnings.warn(
            f"no kickoff time for {sorted(missing)} in week {week}: their games read as not "
            "started, so live odds and locked lineups may be wrong",
            stacklevel=2,
        )
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
