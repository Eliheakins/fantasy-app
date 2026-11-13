"""This week's lineup holes and IR moves for my team (`holes`), and the league's IR rules."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl

from fantasy._bracket import label_for
from fantasy._engine import _id_map, _league, _names, _read, _week_values
from fantasy._lineup import _flag_status, _is_out, _week_games
from fantasy.config import SKILL_POSITIONS
from fantasy.sim import moves
from fantasy.sim.bracket import settings_dict
from fantasy.sim.lineup import CONSTANT_SLOTS, Player, auto_lineup, lineup_slots
from fantasy.sim.lineup import ELIGIBLE as SLOT_ELIGIBLE
from fantasy.sim.odds import LeagueData
from fantasy.sim.roster import free_agents, ros_value
from fantasy.teams import TEAM_MAP

UNAVAILABLE = frozenset({"Out", "Doubtful", "IR", "PUP", "Sus", "NFI"})
FILL_INS = 3
BASE_IR_STATUSES = frozenset({"IR", "PUP"})
RESERVE_STATUSES = {  # Sleeper's reserve_allow_<key> settings -> injury status
    "out": "Out", "doubtful": "Doubtful", "sus": "Sus", "na": "NA", "dnr": "DNR", "cov": "COV",
}  # fmt: skip
NO_GAME_LABELS = frozenset({"Bye this round", "Eliminated", "Champion"})

HoleKind = Literal["bye", "out", "empty"]


def _kd_owned(kind: str, rostered: pl.DataFrame, data_dir: Path | None) -> pl.DataFrame:
    """Rostered K or DEF rows (every roster column) with their `unit`: the nflverse id for a
    kicker, the team code for a defense."""
    players = _read("sleeper_players", data_dir).select("sleeper_id", "full_name", "position")
    if kind == "DEF":
        owned = rostered.join(players, on="sleeper_id").filter(pl.col("position") == "DEF")
        return owned.with_columns(
            pl.col("sleeper_id")
            .replace_strict(TEAM_MAP, default=pl.col("sleeper_id"))
            .alias("unit")
        )
    id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
    owned = rostered.join(id_map, on="sleeper_id").join(players, on="sleeper_id")
    return owned.filter(pl.col("position") == "K").rename({"gsis_id": "unit"})


def _kd_names(kind: str, units: pl.Series, data_dir: Path | None) -> dict[str, str]:
    if kind == "DEF":
        return {u: f"{u} D/ST" for u in units}
    return _names(data_dir)


def _unavailable(data: LeagueData, gsis_id: str) -> bool:
    return _flag_status(data, gsis_id) in UNAVAILABLE or _is_out(data, gsis_id)


@dataclass(frozen=True)
class HoleInputs:
    """Everything `find_holes` reads, as plain values. `value` of a Player is this week's
    projection (0 when he has none); `startable` holds ids with a known kickoff still ahead."""

    slots: tuple[str, ...]
    starters: tuple[Player, ...]
    bench: tuple[Player, ...]
    free: tuple[Player, ...]
    out: frozenset[str]
    bye: frozenset[str]
    startable: frozenset[str]
    ros: dict[str, float]
    names: dict[str, str]


def find_holes(i: HoleInputs) -> list[dict[str, Any]]:
    """Starting slots left with nobody playing (bye, out, empty) that no bench player covers,
    each with the best free agents for it. A bench player covers one hole at most."""
    skill_slots = [s for s in i.slots if s not in CONSTANT_SLOTS]
    placed = auto_lineup([p for p in i.starters if p.position in SKILL_POSITIONS], skill_slots)
    empty = list(skill_slots)
    for slot, _ in placed.slots:
        empty.remove(slot)
    kd_placed: list[tuple[str, str]] = []
    for slot in (s for s in i.slots if s in CONSTANT_SLOTS):
        used = {pid for _, pid in kd_placed}
        unit = next((p for p in i.starters if p.position == slot and p.id not in used), None)
        if unit is None:
            empty.append(slot)
        else:
            kd_placed.append((slot, unit.id))
    found: list[tuple[HoleKind, str, str | None]] = []
    for slot, held in [*placed.slots, *kd_placed]:
        why: HoleKind | None = "bye" if held in i.bye else "out" if held in i.out else None
        if why:
            found.append((why, slot, held))
    found += [("empty", slot, None) for slot in empty]
    cover = sorted(
        (p for p in i.bench if p.id in i.startable and p.id not in i.out and p.id not in i.bye),
        key=lambda p: (-p.value, p.id),
    )
    droppable = (p for p in i.bench if p.position in SKILL_POSITIONS)  # K/DEF have no ros value
    drop = min(droppable, key=lambda p: (i.ros.get(p.id, 0.0), p.id), default=None)
    drop_name = i.names.get(drop.id, drop.id) if drop else None
    rows: list[dict[str, Any]] = []
    for kind, slot, pid in found:
        fits = SLOT_ELIGIBLE.get(slot, frozenset({slot}))
        taken = next((p for p in cover if p.position in fits), None)
        if taken is not None:
            cover.remove(taken)
            continue
        fills = sorted(
            (p for p in i.free if p.position in fits and p.id in i.startable and p.id not in i.out),
            key=lambda p: (-p.value, p.id),
        )[:FILL_INS]
        rows.append(
            {
                "kind": kind,
                "slot": slot,
                "player_name": i.names.get(pid, pid) if pid else None,
                "fill_ins": [
                    {
                        "gsis_id": p.id,
                        "full_name": i.names.get(p.id, p.id),
                        "position": p.position,
                        "projection": p.value,
                        "drop_name": drop_name,
                    }
                    for p in fills
                ],
            }
        )
    return rows


def reserve_rules(settings_json: str | None) -> tuple[int, frozenset[str]]:
    """IR slots a league has and the injury statuses that may use them. Missing or unreadable
    settings mean no slots."""
    settings = settings_dict(settings_json)
    slots = settings.get("reserve_slots")
    allowed = {
        status
        for key, status in RESERVE_STATUSES.items()
        if settings.get(f"reserve_allow_{key}") == 1
    }
    return (slots if isinstance(slots, int) else 0), BASE_IR_STATUSES | allowed


def league_reserve(league_id: str, data_dir: Path | None) -> tuple[int, frozenset[str]]:
    """`reserve_rules` for a league's row in the `leagues` table."""
    raw = _read("leagues", data_dir).filter(pl.col("league_id") == league_id)
    settings = raw["settings"].first() if "settings" in raw.columns and raw.height else None
    return reserve_rules(settings if isinstance(settings, str) else None)


def ir_moves(
    bench_status: dict[str, str], open_slots: int, allowed: frozenset[str], names: dict[str, str]
) -> list[dict[str, Any]]:
    """Bench players who may go to IR, as many as there are open IR slots (by id order)."""
    eligible = sorted(i for i, s in bench_status.items() if s in allowed)[: max(open_slots, 0)]
    return [
        {"kind": "ir_move", "slot": "IR", "player_name": names.get(i, i), "fill_ins": []}
        for i in eligible
    ]


@dataclass(frozen=True)
class _KdSide:
    starters: tuple[Player, ...] = ()
    bench: tuple[Player, ...] = ()
    free: tuple[Player, ...] = ()
    bye: frozenset[str] = frozenset()
    startable: frozenset[str] = frozenset()
    names: dict[str, str] = field(default_factory=dict)


def _kd_side(
    kind: str,
    data: LeagueData,
    mine: int,
    games: tuple[dict[str, datetime], set[str], dict[str, str], datetime],
    data_dir: Path | None,
) -> _KdSide:
    """My K or DEF units, the free ones with this week's projection, and which have a game."""
    kicks, playing, team_of, now = games
    proj = _read("streaming_projection", data_dir, area="derived").filter(
        (pl.col("league_id") == data.league_id) & (pl.col("kind") == kind)
    )
    team_by_unit = dict(zip(proj["unit"], proj["team"], strict=True))
    this_week = dict(
        proj.filter(pl.col("week") == data.current_week)
        .group_by("unit")
        .agg(pl.col("projection").sum())
        .iter_rows()
    )
    rostered = _read("rosters", data_dir).filter(pl.col("league_id") == data.league_id)
    owned = _kd_owned(kind, rostered, data_dir)

    def team_code(u: str) -> str | None:
        return team_by_unit.get(u) or team_of.get(u) or (u if kind == "DEF" else None)

    def mine_where(starter: bool) -> tuple[Player, ...]:
        rows = owned.filter(
            (pl.col("roster_id") == mine) & ~pl.col("is_ir") & (pl.col("is_starter") == starter)
        )
        return tuple(Player(u, kind, float(this_week.get(u, 0.0))) for u in rows["unit"])

    taken = set(owned["unit"])
    free = tuple(Player(u, kind, float(v)) for u, v in this_week.items() if u not in taken)
    units = {p.id for p in (*mine_where(True), *mine_where(False), *free)}
    teams = {u: team_code(u) for u in units}
    return _KdSide(
        starters=mine_where(True),
        bench=mine_where(False),
        free=free,
        bye=frozenset(u for u, t in teams.items() if playing and t and t not in playing),
        startable=frozenset(u for u, t in teams.items() if t in kicks and kicks[t] > now),
        names=_kd_names(kind, proj["unit"].unique(), data_dir),
    )


def _no_game(data: LeagueData, mine: int) -> bool:
    """True from the playoff start when my team has no game this week: a bye, out of (or never in)
    the bracket, champion, or the season is over."""
    week = data.current_week
    if week < data.playoff_start:
        return False
    if week >= data.playoff_start + data.playoff_weeks:
        return True
    label = label_for(
        data.bracket, data.team_names, mine, week, week, data.playoff_start, data.round_type
    )
    return label is None or label in NO_GAME_LABELS


def holes(
    league_key: str,
    data_dir: Path | None = None,
    team: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """This week's lineup holes and IR moves for my team (see `find_holes`, `ir_moves`); none in a
    playoff week my team does not play."""
    data, mine = _league(league_key, data_dir, team)
    if _no_game(data, mine):
        return []
    week, now = data.current_week, now or datetime.now(UTC)
    positions = moves.position_of(data)
    values = _week_values(data, week, positions)
    names = _names(data_dir)
    ids = _id_map(data_dir, "nfl_team").filter(pl.col("gsis_id").is_not_null())
    mine_rows = (
        _read("rosters", data_dir)
        .filter((pl.col("league_id") == data.league_id) & (pl.col("roster_id") == mine))
        .join(ids, on="sleeper_id")
    )
    kicks, playing = _week_games(week, data_dir)
    team_of = dict(zip(ids["gsis_id"], ids["nfl_team"], strict=True))
    bye = frozenset(g for g, t in team_of.items() if playing and t is not None and t not in playing)
    startable = frozenset(g for g, t in team_of.items() if t in kicks and kicks[t] > now)

    def player(g: str) -> Player:
        return Player(g, positions[g], values.get(g, 0.0))

    def usable(g: str) -> bool:
        return g in positions and positions[g] in SKILL_POSITIONS

    def role(starter: bool, ir: bool) -> list[str]:
        r = mine_rows.filter(pl.col("is_starter") == starter, pl.col("is_ir") == ir)
        return [g for g in r["gsis_id"] if usable(g)]

    starters, bench, on_ir = role(True, False), role(False, False), role(False, True)
    free = [g for g in free_agents(data) if g in values]
    unavailable = frozenset(g for g in (*starters, *bench, *free) if _unavailable(data, g))
    sides = [
        _kd_side(k, data, mine, (kicks, playing, team_of, now), data_dir)
        for k in sorted(CONSTANT_SLOTS)
        if k in data.roster_positions
    ]
    kd_ids = [p.id for side in sides for p in side.bench]
    kd_out = frozenset(
        p.id
        for side in sides
        for p in (*side.starters, *side.bench, *side.free)
        if p.position == "K" and _unavailable(data, p.id)
    )
    inputs = HoleInputs(
        slots=(
            *lineup_slots(data.roster_positions),
            *(s for s in data.roster_positions if s in CONSTANT_SLOTS),
        ),
        starters=(*(player(g) for g in starters), *(p for x in sides for p in x.starters)),
        bench=(*(player(g) for g in bench if g in values), *(p for x in sides for p in x.bench)),
        free=(*(player(g) for g in free), *(p for x in sides for p in x.free)),
        out=unavailable | kd_out,
        bye=bye.union(*(x.bye for x in sides)),
        startable=startable.union(*(x.startable for x in sides)),
        ros=ros_value(data, [*bench, *kd_ids]),
        names=names | {k: v for x in sides for k, v in x.names.items()},
    )
    reserve, allowed = league_reserve(data.league_id, data_dir)
    status = {g: _flag_status(data, g) for g in bench}
    return [*find_holes(inputs), *ir_moves(status, reserve - len(on_ir), allowed, names)]
