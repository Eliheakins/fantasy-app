"""The playoff bracket as the league plays it: the winners bracket with each side's chance to
advance (`bracket`) and a one-line status for a team in a playoff week (`label_for`, the pure
rule; `playoff_status` and `league_label` read the tables for it).

Both read the synced `playoff_brackets` rows, which are trusted only once the playoffs start
(current week >= playoff week start), the same rule the season simulation follows.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from fantasy._engine import _league_settings, _read
from fantasy._leagues import my_league
from fantasy.sim.bracket import (
    Match,
    from_rows,
    is_title_path,
    round_of_week,
    round_type_of,
    round_weeks,
    seeds_from,
    template,
)

log = logging.getLogger(__name__)
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}
BYE, ELIMINATED, CHAMPION = "Bye this round", "Eliminated", "Champion"


@dataclass(frozen=True)
class BracketView:
    """`rounds` is empty and `message` says why when there is no bracket to show."""

    rounds: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None


def _ordinal(n: int) -> str:
    return ORDINALS.get(n, f"{n}th")


def _matches(league_id: str, data_dir: Path | None) -> tuple[Match, ...]:
    table = _read("playoff_brackets", data_dir).filter(pl.col("league_id") == league_id)
    return from_rows(table.iter_rows(named=True))


def _round_type(league_id: str, data_dir: Path | None) -> int:
    return round_type_of(_league_settings(league_id, data_dir))


def _names(league_id: str, data_dir: Path | None) -> dict[int, str]:
    teams = _read("league_teams", data_dir).filter(pl.col("league_id") == league_id)
    return {int(r): str(n) for r, n in zip(teams["roster_id"], teams["team_name"], strict=True)}


def _side(slot: Any, names: dict[int, str], seeds: dict[int, int]) -> dict[str, Any]:
    team = slot if isinstance(slot, int) else None
    kind, source = slot if isinstance(slot, tuple) else (None, None)
    return {
        "roster_id": team,
        "team_name": None if team is None else names.get(team, str(team)),
        "seed": seeds.get(team) if team is not None else None,
        "from_kind": kind,
        "from_m": source,
    }


def bracket(league_key: str, data_dir: Path | None = None, team: int | None = None) -> BracketView:
    """The winners bracket by round: matches with sides, winner once played and each side's
    chance to win the round (`sim_bracket`; none for placement games or played matches)."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        raise ValueError(f"unknown league {league_key!r}")
    start, lid = int(me["playoff_week_start"]), me["league_id"]
    if int(me["current_week"]) < start:
        return BracketView(message=f"The bracket is set after week {start - 1}")
    matches = [m for m in _matches(lid, data_dir) if m.bracket == "winners"]
    if not matches:
        return BracketView(message="No bracket has been synced for this league yet")
    names = _names(lid, data_dir)
    n_rounds, round_type = max(m.r for m in matches), _round_type(lid, data_dir)
    order = (
        seeds_from(tuple(matches), template(int(me.get("playoff_teams") or 6), round_type)) or []
    )
    seeds = {rid: i + 1 for i, rid in enumerate(order)}
    odds = _read("sim_bracket", data_dir, area="derived").filter(pl.col("league_id") == lid)
    p_win = {
        (int(r), int(k)): p for r, k, p in odds.select("roster_id", "round", "p_win").iter_rows()
    }
    mine = int(me["roster_id"])

    def chance(match: Match, slot: Any) -> float | None:
        if match.w is not None or not is_title_path(match) or not isinstance(slot, int):
            return None
        return p_win.get((slot, match.r))

    rounds = [
        {
            "round": r,
            "weeks": list(round_weeks(r, start, round_type, n_rounds)),
            "matches": [
                {
                    "m": m.m, "place": m.p, "winner": m.w,
                    "t1": _side(m.t1, names, seeds), "t2": _side(m.t2, names, seeds),
                    "t1_p_win": chance(m, m.t1), "t2_p_win": chance(m, m.t2),
                    "is_mine": mine in (m.t1, m.t2),
                }
                for m in sorted(matches, key=lambda x: x.m)
                if m.r == r
            ],
        }
        for r in sorted({m.r for m in matches})
    ]  # fmt: skip
    return BracketView(rounds=rounds)


def _match_of(matches: tuple[Match, ...], kind: str, roster_id: int, round_no: int) -> Match | None:
    return next(
        (m for m in matches if m.bracket == kind and m.r == round_no and roster_id in (m.t1, m.t2)),
        None,
    )


def _opponent(match: Match, roster_id: int, names: dict[int, str]) -> str:
    other = match.t2 if match.t1 == roster_id else match.t1
    return names.get(other, str(other)) if isinstance(other, int) else "TBD"


def status_of(
    matches: tuple[Match, ...], names: dict[int, str], roster_id: int, round_no: int
) -> str | None:
    """Where a team stands in playoff round `round_no`, from the bracket rows alone."""
    title = [m for m in matches if m.bracket == "winners" and is_title_path(m)]
    final = next((m for m in title if m.p == 1), None)
    if final is not None and final.w == roster_id and round_no >= final.r:
        return CHAMPION
    here = _match_of(matches, "winners", roster_id, round_no)
    if here is not None:
        if is_title_path(here):
            return f"Round {round_no} vs {_opponent(here, roster_id, names)}"
        if here.p:
            return (
                f"Consolation: {_ordinal(here.p)} place game vs {_opponent(here, roster_id, names)}"
            )
        return None
    losers = _match_of(matches, "losers", roster_id, round_no)
    if losers is not None:  # Sleeper numbers losers-bracket places from 1, so no place here
        return f"Consolation game vs {_opponent(losers, roster_id, names)}"
    if any(m.r > round_no and roster_id in (m.t1, m.t2) for m in title):
        return BYE
    if any(m.r < round_no and m.l == roster_id for m in title):
        return ELIMINATED
    return None


def label_for(
    matches: tuple[Match, ...],
    names: dict[int, str],
    *,
    roster_id: int,
    week: int,
    current_week: int,
    playoff_start: int,
    round_type: int,
) -> str | None:
    """`status_of` for an NFL week: None before the playoffs start (the rows are not trusted yet),
    for a regular-season week, or with no winners bracket rows."""
    if current_week < playoff_start or week < playoff_start:
        return None
    winners = [m.r for m in matches if m.bracket == "winners"]
    if not winners:
        return None
    round_no = round_of_week(week, playoff_start, round_type, max(winners))
    return status_of(matches, names, roster_id, round_no)


def _label(
    league_id: str,
    roster_id: int,
    week: int,
    current_week: int,
    playoff_start: int,
    data_dir: Path | None,
) -> str | None:
    if current_week < playoff_start or week < playoff_start:
        return None  # skips the table reads outside the playoffs
    return label_for(
        _matches(league_id, data_dir), _names(league_id, data_dir), roster_id=roster_id,
        week=week, current_week=current_week, playoff_start=playoff_start,
        round_type=_round_type(league_id, data_dir),
    )  # fmt: skip


def playoff_status(
    league_key: str, roster_id: int, week: int, data_dir: Path | None = None
) -> str | None:
    """ "Round N vs <team>", "Bye this round", "Eliminated", "Champion" or a consolation line;
    None outside the playoffs or before the bracket is set. Deterministic, no simulation."""
    me = my_league(league_key, data_dir)
    if me is None:
        raise ValueError(f"unknown league {league_key!r}")
    current, start = int(me["current_week"]), int(me["playoff_week_start"])
    return _label(me["league_id"], roster_id, week, current, start, data_dir)


def league_label(row: Mapping[str, Any], data_dir: Path | None = None) -> str | None:
    """`playoff_status` for a `leagues` row's team in the league's current week (None without a
    team or week, or when the stored bracket rows cannot be read; logged)."""
    roster_id, week, start = (
        row.get("roster_id"),
        row.get("current_week"),
        row.get("playoff_week_start"),
    )
    if roster_id is None or week is None or start is None:
        return None
    try:
        return _label(row["league_id"], int(roster_id), int(week), int(week), int(start), data_dir)
    except ValueError:  # corrupt stored bracket rows: one league must not break the list
        log.warning("league %s: unreadable playoff bracket", row.get("league_key"), exc_info=True)
        return None
