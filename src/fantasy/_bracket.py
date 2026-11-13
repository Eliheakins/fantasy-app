"""The playoff bracket as the league plays it: the winners bracket with each side's chance to
advance (`bracket`), my team's playoff state in a week (`team_phase`, the one classifier) and the
one-line status derived from it (`label_for`; `playoff_status`, `league_label` and `league_phase`
read the tables for them).

All read only the fixed `playoff_brackets` rows (`sim.bracket.bracket_trust`: synced once
Sleeper's week reached the playoff start), the same rows the season simulation trusts.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import polars as pl

from fantasy._engine import _league_settings, _read
from fantasy._leagues import my_league
from fantasy.sim.bracket import (
    Match,
    fixed_only,
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
NO_BRACKET = "No bracket has been synced for this league yet"
TeamPhase = Literal["regular", "playing", "bye", "consolation", "eliminated", "champion", "over"]
NO_GAME_PHASES: frozenset[TeamPhase] = frozenset({"bye", "eliminated", "champion", "over"})


@dataclass(frozen=True)
class BracketView:
    """`rounds` is empty and `message` says why when there is no bracket to show."""

    rounds: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None


def _ordinal(n: int) -> str:
    return ORDINALS.get(n, f"{n}th")


def _matches(league_id: str, playoff_start: int, data_dir: Path | None) -> tuple[Match, ...]:
    """The league's fixed bracket rows (provisional ones are no seeds yet)."""
    table = _read("playoff_brackets", data_dir).filter(pl.col("league_id") == league_id)
    return fixed_only(from_rows(table.iter_rows(named=True)), playoff_start)


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
    start, lid, current = int(me["playoff_week_start"]), me["league_id"], int(me["current_week"])
    not_set = BracketView(message=f"The bracket is set after week {start - 1}")
    if current < start:
        return not_set
    matches = [m for m in _matches(lid, start, data_dir) if m.bracket == "winners"]
    if not matches:  # in the first playoff week Sleeper may not have fixed the seeds yet
        return not_set if current == start else BracketView(message=NO_BRACKET)
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


@dataclass(frozen=True)
class _Standing:
    phase: TeamPhase | None
    game: Match | None = None  # my game this week, for the opponent in the label
    lost_title_game: bool = False


def _pending(matches: tuple[Match, ...], roster_id: int, round_no: int) -> bool:
    """A slot this round still reads "winner/loser of match k" for a match of mine whose result
    could put my team there."""
    mine = {m.m: m for m in matches if m.bracket == "winners" and roster_id in (m.t1, m.t2)}
    for m in matches:
        if m.bracket != "winners" or m.r != round_no:
            continue
        for slot in (m.t1, m.t2):
            if isinstance(slot, tuple) and slot[1] in mine:
                result = mine[slot[1]].w if slot[0] == "w" else mine[slot[1]].l
                if result in (None, roster_id):
                    return True
    return False


def _never_in_bracket(matches: tuple[Match, ...], roster_id: int) -> bool:
    """The winners bracket's first round is fully seeded (every side a team) and my team is on no
    winners or losers row: rows still missing or unseeded prove nothing."""
    winners = [m for m in matches if m.bracket == "winners"]
    if not winners:
        return False
    first = min(m.r for m in winners)
    seeded = all(isinstance(s, int) for m in winners if m.r == first for s in (m.t1, m.t2))
    return seeded and all(roster_id not in (m.t1, m.t2) for m in matches)


def _standing(
    matches: tuple[Match, ...], roster_id: int, week: int, playoff_start: int,
    playoff_weeks: int, round_type: int,
) -> _Standing:  # fmt: skip
    if week < playoff_start:
        return _Standing("regular")
    title = [m for m in matches if m.bracket == "winners" and is_title_path(m)]
    final = next((m for m in title if m.p == 1), None)
    won_final = final is not None and final.w == roster_id
    lost_title = any(m.l == roster_id for m in title)
    if week >= playoff_start + playoff_weeks:  # the season is over
        return _Standing("champion" if won_final else "over", lost_title_game=lost_title)
    winners = [m.r for m in matches if m.bracket == "winners"]
    if not winners:
        return _Standing(None)
    round_no = round_of_week(week, playoff_start, round_type, max(winners))
    if won_final and final is not None and round_no >= final.r:
        return _Standing("champion")
    here = _match_of(matches, "winners", roster_id, round_no)
    if here is not None:
        if is_title_path(here):
            return _Standing("playing", here)
        return _Standing("consolation" if here.p else None, here)
    losers = _match_of(matches, "losers", roster_id, round_no)
    if losers is not None:
        return _Standing("consolation", losers)
    if any(m.r > round_no and roster_id in (m.t1, m.t2) for m in title):
        return _Standing("bye")
    if _pending(matches, roster_id, round_no):
        return _Standing(None)
    lost_before = any(m.r < round_no and m.l == roster_id for m in title)
    if lost_before or _never_in_bracket(matches, roster_id):
        return _Standing("eliminated", lost_title_game=lost_before)
    return _Standing(None)


def team_phase(
    matches: tuple[Match, ...],
    *,
    roster_id: int,
    week: int,
    playoff_start: int,
    playoff_weeks: int,
    round_type: int,
) -> TeamPhase | None:
    """My team's playoff state in an NFL week, from fixed bracket rows. Bye, eliminated, champion
    and over need positive evidence; None when it cannot be decided (no fixed rows yet, my slot
    still "winner/loser of match k"). A consolation game counts as a game."""
    return _standing(
        matches, roster_id, week, playoff_start, playoff_weeks, round_type
    ).phase  # fmt: skip


def label_for(
    matches: tuple[Match, ...],
    names: dict[int, str],
    *,
    roster_id: int,
    week: int,
    playoff_start: int,
    playoff_weeks: int,
    round_type: int,
) -> str | None:
    """The one-line status for `team_phase`: "Round N vs X", "Bye this round", "Eliminated",
    "Champion" or a consolation line; None in the regular season or when the phase is unknown.
    "Eliminated" only for a team that lost a title-path game (a team that missed the playoffs
    has no label)."""
    st = _standing(matches, roster_id, week, playoff_start, playoff_weeks, round_type)
    game = st.game
    if st.phase in ("playing", "consolation") and game is not None:
        vs = _opponent(game, roster_id, names)
        if st.phase == "playing":
            return f"Round {game.r} vs {vs}"
        if game.bracket == "losers":  # Sleeper numbers losers-bracket places from 1, so no place
            return f"Consolation game vs {vs}"
        return f"Consolation: {_ordinal(game.p or 0)} place game vs {vs}"
    if st.phase == "bye":
        return BYE
    if st.phase == "champion":
        return CHAMPION
    if st.phase in ("eliminated", "over") and st.lost_title_game:
        return ELIMINATED
    return None


def _label(
    league_id: str, roster_id: int, week: int, playoff_start: int, playoff_weeks: int,
    data_dir: Path | None,
) -> str | None:  # fmt: skip
    if week < playoff_start:
        return None  # skips the table reads outside the playoffs
    return label_for(
        _matches(league_id, playoff_start, data_dir), _names(league_id, data_dir),
        roster_id=roster_id, week=week, playoff_start=playoff_start,
        playoff_weeks=playoff_weeks, round_type=_round_type(league_id, data_dir),
    )  # fmt: skip


def _phase(
    league_id: str, roster_id: int, week: int, playoff_start: int, playoff_weeks: int,
    data_dir: Path | None,
) -> TeamPhase | None:  # fmt: skip
    if week < playoff_start:
        return "regular"  # skips the table reads outside the playoffs
    return team_phase(
        _matches(league_id, playoff_start, data_dir), roster_id=roster_id, week=week,
        playoff_start=playoff_start, playoff_weeks=playoff_weeks,
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
    if me["playoff_weeks"] is None:
        return None
    start, weeks = int(me["playoff_week_start"]), int(me["playoff_weeks"])
    return _label(me["league_id"], roster_id, week, start, weeks, data_dir)


def _for_row[T](
    row: Mapping[str, Any],
    read: Callable[[str, int, int, int, int, Path | None], T | None],
    data_dir: Path | None,
) -> T | None:
    """`read` for a `leagues` row's team in the league's current week: None without a team, week
    or bracket length, or when the stored bracket rows cannot be read (logged)."""
    roster_id, week = row.get("roster_id"), row.get("current_week")
    start, weeks = row.get("playoff_week_start"), row.get("playoff_weeks")
    if roster_id is None or week is None or start is None or weeks is None:
        return None
    try:
        return read(row["league_id"], int(roster_id), int(week), int(start), int(weeks), data_dir)
    except ValueError:  # corrupt stored bracket rows: one league must not break the list
        log.warning("league %s: unreadable playoff bracket", row.get("league_key"), exc_info=True)
        return None


def league_label(row: Mapping[str, Any], data_dir: Path | None = None) -> str | None:
    """`playoff_status` for a `leagues` row's team in the league's current week (best effort)."""
    return _for_row(row, _label, data_dir)


def league_phase(row: Mapping[str, Any], data_dir: Path | None = None) -> TeamPhase | None:
    """`team_phase` for a `leagues` row's team in the league's current week (best effort, like
    `league_label`)."""
    return _for_row(row, _phase, data_dir)
