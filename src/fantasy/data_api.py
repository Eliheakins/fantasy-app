"""The only module the dashboard imports: pure reads over the parquet store, no Streamlit.

Tables that no stage has written yet come back empty with the right columns, never as errors.
Engine outputs that do not exist yet (lineup, waivers, odds, trades) return empty frames.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.availability import locked_teams
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots, lineup_with_locks
from fantasy.sim.odds import LeagueData
from fantasy.sim.sampler import LEVELS, Slate, correlation_matrix, sample_points
from fantasy.sim.winprob import choose, swap_candidates

POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
ROSTER_COLUMNS = [
    "sleeper_id",
    "full_name",
    "position",
    "team",
    "injury_status",
    "is_starter",
    "is_ir",
]

_S, _F, _B = pl.String, pl.Float64, pl.Boolean
# Shapes of engine outputs, filled in by later stories (E4, E5).
_ENGINE_STUBS: dict[str, dict[str, pl.DataType | type[pl.DataType]]] = {
    "lineup": {
        "slot": _S,
        "gsis_id": _S,
        "full_name": _S,
        "position": _S,
        "projection": _F,
        "p10": _F,
        "p90": _F,
        "starting_now": _B,
        "recommended": _B,
        "injury": _S,
        "locked": _B,
    },
    "win_probability": {
        "option": _S,
        "win_prob": _F,
        "expected_points": _F,
        "gsis_ids": pl.List(_S),
        "share_better": _F,
        "tag": _S,
    },
    "waivers": {
        "gsis_id": _S,
        "full_name": _S,
        "position": _S,
        "drop_name": _S,
        "delta_points": _F,
        "playoff_delta": _F,
        "title_delta": _F,
        "se_title": _F,
    },
    "season_odds": {
        "roster_id": pl.Int64,
        "team_name": _S,
        "p_playoffs": _F,
        "p_bye": _F,
        "p_title": _F,
        "exp_wins": _F,
        "is_me": _B,
    },
    "kdef": {"team": _S, "position": _S, "week": _S, "projection": _F},
}


def _read(name: str, data_dir: Path, area: str = "raw") -> pl.DataFrame:
    try:
        return store.read_table(name, area, data_dir)
    except FileNotFoundError:
        return pl.DataFrame(schema=store.SCHEMAS[name])


def scoring_labels(scoring: dict[str, float], roster_positions: list[str]) -> list[str]:
    labels = [f"{scoring.get('rec', 0):g} PPR", f"{scoring.get('pass_td', 0):g}-pt pass TD"]
    if scoring.get("pass_int"):
        labels.append(f"{scoring['pass_int']:g} per INT")
    if "SUPER_FLEX" in roster_positions:
        labels.append("Superflex")
    return labels


def leagues(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """One row per league with my team, record and scoring labels."""
    mine = _read("league_teams", data_dir).filter(pl.col("is_me"))
    joined = _read("leagues", data_dir).join(mine, on="league_id", how="left")
    labels = [
        ", ".join(scoring_labels(json.loads(scoring), positions))
        for scoring, positions in zip(
            joined["scoring_settings"], joined["roster_positions"], strict=True
        )
    ]
    return joined.with_columns(pl.Series("scoring_labels", labels, dtype=pl.String)).select(
        "league_key",
        "league_id",
        "name",
        "current_week",
        "num_teams",
        "roster_id",
        "team_name",
        "wins",
        "losses",
        "ties",
        "points_for",
        "scoring_labels",
    )


def roster(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """My roster in a league: starters first, then by position."""
    schema = {c: store.SCHEMAS["sleeper_players"].get(c, pl.Boolean) for c in ROSTER_COLUMNS}
    row = leagues(data_dir).filter(pl.col("league_key") == league_key)
    if row.is_empty():
        return pl.DataFrame(schema=schema)
    league_id, roster_id = row["league_id"][0], row["roster_id"][0]
    mine = _read("rosters", data_dir).filter(
        (pl.col("league_id") == league_id) & (pl.col("roster_id") == roster_id)
    )
    players = _read("sleeper_players", data_dir).select(
        "sleeper_id", "full_name", "position", "team", "injury_status"
    )
    return (
        mine.join(players, on="sleeper_id", how="left")
        .with_columns(
            pl.col("position")
            .replace_strict(POSITION_ORDER, default=len(POSITION_ORDER))
            .alias("_order")
        )
        .sort(["is_starter", "_order", "full_name"], descending=[True, False, False])
        .select(ROSTER_COLUMNS)
    )


def unmatched(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Active non-DEF players with no nflverse ID (shown as "no history")."""
    id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
    return (
        _read("sleeper_players", data_dir)
        .filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position") != "DEF")
        .select("sleeper_id", "full_name", "position", "team")
        .join(id_map, on="sleeper_id", how="left")
        .filter(pl.col("gsis_id").is_null())
        .select("sleeper_id", "full_name", "position", "team")
        .sort("position", "full_name")
    )


def lineup(league_key: str, week: int = 0, now: datetime | None = None) -> pl.DataFrame:
    """My best lineup by projected points for a remaining week, plus the bench.

    `starting_now` marks who is set to start in Sleeper (only known for the current week).
    p10 and p90 come from how actual points have scattered around projections.
    """
    data, mine = _league(league_key)
    week = week or data.current_week
    names, positions = _names(), moves.position_of(data)
    values = moves.week_values(data).get(week, {})
    pool = [Player(i, positions[i], values[i]) for i in moves.team_ids(data, mine) if i in values]
    marginals = _read("marginals", store.DATA_DIR, area="derived").filter(
        pl.col("league_id") == data.league_id
    )
    ratio = {
        (r["position"], round(r["tau"], 2)): r["ratio"] for r in marginals.iter_rows(named=True)
    }
    starting: set[str] = set()
    if week == data.current_week:
        ids = _read("id_map", store.DATA_DIR, area="derived").select("sleeper_id", "gsis_id")
        set_starters = (
            _read("matchup_players", store.DATA_DIR)
            .filter(
                (pl.col("league_id") == data.league_id)
                & (pl.col("week") == week)
                & (pl.col("roster_id") == mine)
                & pl.col("is_starter")
            )
            .join(ids, on="sleeper_id")
        )
        starting = set(set_starters["gsis_id"].to_list())

    status, locked = _status_and_locks(week, data.current_week, now)
    best = lineup_with_locks(
        pool, lineup_slots(data.roster_positions), {p.id for p in pool if p.id in locked}, starting
    )
    slot_of = {pid: slot for slot, pid in best.slots}

    rows = []
    for p in sorted(pool, key=lambda p: (p.id not in slot_of, -p.value)):
        rows.append(
            {
                "slot": slot_of.get(p.id, "BN"),
                "gsis_id": p.id,
                "full_name": names.get(p.id, p.id),
                "position": p.position,
                "projection": p.value,
                "p10": p.value * ratio.get((p.position, 0.1), 0.0),
                "p90": p.value * ratio.get((p.position, 0.9), 0.0),
                "starting_now": p.id in starting,
                "recommended": p.id in slot_of,
                "injury": status.get(p.id),
                "locked": p.id in locked,
            }
        )
    return pl.DataFrame(rows, schema=_ENGINE_STUBS["lineup"])


def _status_and_locks(
    week: int, current_week: int, now: datetime | None = None
) -> tuple[dict[str, str], set[str]]:
    """Injury status by nflverse ID, and ids whose game has started (current week only)."""
    ids = _read("id_map", store.DATA_DIR, area="derived").select(
        "sleeper_id", "gsis_id", "nfl_team"
    )
    players = _read("sleeper_players", store.DATA_DIR).select("sleeper_id", "injury_status")
    joined = ids.join(players, on="sleeper_id").filter(pl.col("gsis_id").is_not_null())
    status = {g: s for g, s in zip(joined["gsis_id"], joined["injury_status"], strict=True) if s}
    if week != current_week:
        return status, set()
    started = locked_teams(
        _read("nfl_schedules", store.DATA_DIR), load_config().season, week, now or datetime.now(UTC)
    )
    locked = set(joined.filter(pl.col("nfl_team").is_in(started))["gsis_id"].to_list())
    return status, locked


def _names() -> dict[str, str]:
    """nflverse ID -> player name."""
    ids = _read("id_map", store.DATA_DIR, area="derived").select("sleeper_id", "gsis_id")
    players = _read("sleeper_players", store.DATA_DIR).select("sleeper_id", "full_name")
    joined = ids.join(players, on="sleeper_id").filter(pl.col("gsis_id").is_not_null())
    return dict(zip(joined["gsis_id"], joined["full_name"], strict=True))


def _league(league_key: str) -> tuple[LeagueData, int]:
    """Simulation inputs for one league and my roster id."""
    from fantasy.stages.simulate import load_league_data  # heavy imports, only when asked

    row = store.read_table("leagues", "raw").filter(pl.col("league_key") == league_key)
    if row.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    league = row.row(0, named=True)
    teams = store.read_table("league_teams", "raw")
    mine = teams.filter((pl.col("league_id") == league["league_id"]) & pl.col("is_me"))
    return load_league_data(league), int(mine["roster_id"][0])


def waivers(league_key: str, week: int = 0) -> pl.DataFrame:
    """Best adds for my team by extra points over the rest of the season (a shortcut)."""
    data, mine = _league(league_key)
    names = _names()
    adds = [w for w in moves.waiver_candidates(data, mine, top_n=15) if w.delta_mu > MIN_GAIN]
    odds = {r["gsis_id"]: r for r in moves.waiver_odds(data, mine, adds).iter_rows(named=True)}
    rows = [
        {
            "gsis_id": w.gsis_id,
            "full_name": names.get(w.gsis_id, w.gsis_id),
            "position": w.position,
            "drop_name": names.get(w.drop_id, w.drop_id),
            "delta_points": w.delta_mu,
            "playoff_delta": odds[w.gsis_id]["playoff_delta"],
            "title_delta": odds[w.gsis_id]["title_delta"],
            "se_title": odds[w.gsis_id]["se_title"],
        }
        for w in adds
    ]
    return pl.DataFrame(rows, schema=_ENGINE_STUBS["waivers"])


def trade_partners(league_key: str) -> pl.DataFrame:
    data, mine = _league(league_key)
    rows = [(r, data.team_names[r]) for r in data.roster_ids if r != mine]
    return pl.DataFrame(rows, schema=["roster_id", "team_name"], orient="row")


def trade_assets(league_key: str, roster_id: int | None = None) -> pl.DataFrame:
    """A roster's skill players with projected points over the rest of the season."""
    data, mine = _league(league_key)
    ids = moves.team_ids(data, mine if roster_id is None else roster_id)
    names, positions, values = _names(), moves.position_of(data), moves.ros_value(data, ids)
    rows = [(i, names.get(i, i), positions[i], values[i]) for i in ids]
    schema = ["gsis_id", "full_name", "position", "ros_points"]
    return pl.DataFrame(rows, schema=schema, orient="row").sort("ros_points", descending=True)


def evaluate_trade(
    league_key: str, partner_roster_id: int, give_ids: list[str], get_ids: list[str]
) -> pl.DataFrame:
    """Playoff and title odds before and after, for me and the partner. May raise ValueError."""
    data, mine = _league(league_key)
    return moves.evaluate_trade(data, mine, partner_roster_id, list(give_ids), list(get_ids))


def trade_roster_changes(
    league_key: str, partner_roster_id: int, give_ids: list[str], get_ids: list[str]
) -> pl.DataFrame:
    """Players dropped or picked up automatically to keep each roster's size."""
    data, mine = _league(league_key)
    after = moves.apply_trade(data, mine, partner_roster_id, list(give_ids), list(get_ids))
    names, positions = _names(), moves.position_of(data)
    rows = []
    sides = ((mine, give_ids, get_ids), (partner_roster_id, get_ids, give_ids))
    for roster_id, sent, received in sides:
        team = data.team_names[roster_id]
        before_ids = set(moves.team_ids(data, roster_id))
        after_ids = set(moves.team_ids(data, roster_id, after))
        for gid in sorted(before_ids - after_ids - set(sent)):
            rows.append((team, "dropped", names.get(gid, gid), positions[gid]))
        for gid in sorted(after_ids - before_ids - set(received)):
            rows.append((team, "picked up", names.get(gid, gid), positions[gid]))
    schema = ["team_name", "action", "full_name", "position"]
    return pl.DataFrame(rows, schema=schema, orient="row")


def season_odds(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Latest simulated playoff and title odds for every team, best title odds first."""
    row = leagues(data_dir).filter(pl.col("league_key") == league_key)
    if row.is_empty():
        return pl.DataFrame(schema=_ENGINE_STUBS["season_odds"])
    odds = _read("sim_season", data_dir, area="derived").filter(
        pl.col("league_id") == row["league_id"][0]
    )
    return (
        odds.with_columns((pl.col("roster_id") == row["roster_id"][0]).alias("is_me"))
        .select(*_ENGINE_STUBS["season_odds"])
        .sort("p_title", descending=True)
    )


def odds_history(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Every saved simulation run for a league: run_at, team_name, p_playoffs, p_title."""
    row = leagues(data_dir).filter(pl.col("league_key") == league_key)
    columns = ["run_at", "team_name", "roster_id", "p_playoffs", "p_title"]
    if row.is_empty():
        return pl.DataFrame(schema={c: store.SCHEMAS["sim_season_history"][c] for c in columns})
    history = _read("sim_season_history", data_dir, area="archive")
    return history.filter(pl.col("league_id") == row["league_id"][0]).select(columns)


def kdef(league_key: str, week: int) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["kdef"])


MIN_GAIN = 0.05  # expected points below this are not worth a roster move
LINEUP_SIMS = 20000
LINEUP_SEED = 11
KD_SEED_OFFSET = 1000  # K and DEF draws are independent of the player draws


def win_probability(
    league_key: str, week: int = 0, n_sims: int = LINEUP_SIMS, now: datetime | None = None
) -> pl.DataFrame:
    """My max-points lineup, the lineup set in Sleeper, and the lineup with the best chance of
    beating this week's opponent, each with its win probability on held-out draws.

    The opponent plays the lineup set in Sleeper, or their best lineup if none is set. Points
    already scored are not used: every player is drawn fresh, locked or not.
    """
    empty = pl.DataFrame(schema=_ENGINE_STUBS["win_probability"])
    data, mine = _league(league_key)
    week = week or data.current_week
    opp = next(
        (b if a == mine else a for a, b in data.pairings.get(week, []) if mine in (a, b)), None
    )
    mine_rows = lineup(league_key, week, now)
    if opp is None or mine_rows.is_empty():
        return empty

    positions, values = moves.position_of(data), moves.week_values(data).get(week, {})
    slots = lineup_slots(data.roster_positions)
    opp_ids = _opponent_lineup(data, opp, week, positions, values, slots)

    base = frozenset(mine_rows.filter(pl.col("recommended"))["gsis_id"])
    locked = set(mine_rows.filter(pl.col("locked"))["gsis_id"])
    bench = [i for i in mine_rows.filter(~pl.col("recommended"))["gsis_id"] if values.get(i, 0) > 0]
    candidates = swap_candidates(base, bench, positions, slots, locked)
    sleeper = frozenset(mine_rows.filter(pl.col("starting_now"))["gsis_id"])
    if sleeper and sleeper not in candidates:
        candidates.append(sleeper)

    ids = sorted({*mine_rows["gsis_id"], *opp_ids})
    points = _draw_points(data, ids, positions, values, week, n_sims)
    column = {i: j for j, i in enumerate(ids)}

    def total(lineup_ids: frozenset[str] | list[str], team_seed: int) -> np.ndarray:
        cols = [column[i] for i in lineup_ids]
        return points[:, cols].sum(axis=1) + _constant_points(data, n_sims, team_seed)

    totals = {c: total(c, LINEUP_SEED + KD_SEED_OFFSET) for c in candidates}
    verdict = choose(candidates, base, totals, total(opp_ids, LINEUP_SEED + KD_SEED_OFFSET + 1))

    mean_of = {r["gsis_id"]: r["projection"] for r in mine_rows.iter_rows(named=True)}
    options = {"max_points": base, "win_prob": verdict.chosen}
    if sleeper:
        options["sleeper_now"] = sleeper
    rows = [
        {
            "option": name,
            "win_prob": verdict.win_prob[ids_],
            "expected_points": sum(mean_of[i] for i in ids_),
            "gsis_ids": sorted(ids_),
            "share_better": verdict.share_better if name == "win_prob" else 0.5,
            "tag": verdict.tag if name == "win_prob" else "",
        }
        for name, ids_ in options.items()
    ]
    return pl.DataFrame(rows, schema=_ENGINE_STUBS["win_probability"])


def _opponent_lineup(
    data: LeagueData,
    opp: int,
    week: int,
    positions: dict[str, str],
    values: dict[str, float],
    slots: list[str],
) -> list[str]:
    """Skill players the opponent starts: set in Sleeper if known, else their best lineup."""
    ids = _read("id_map", store.DATA_DIR, area="derived").select("sleeper_id", "gsis_id")
    set_now = (
        _read("matchup_players", store.DATA_DIR)
        .filter(
            (pl.col("league_id") == data.league_id)
            & (pl.col("week") == week)
            & (pl.col("roster_id") == opp)
            & pl.col("is_starter")
        )
        .join(ids, on="sleeper_id")["gsis_id"]
        .to_list()
    )
    known = [i for i in set_now if i in values and i in positions]
    if week == data.current_week and known:
        return known
    pool = [Player(i, positions[i], values[i]) for i in moves.team_ids(data, opp) if i in values]
    return sorted(auto_lineup(pool, slots).players)


def _draw_points(
    data: LeagueData,
    ids: list[str],
    positions: dict[str, str],
    values: dict[str, float],
    week: int,
    n_sims: int,
) -> np.ndarray:
    """Joint draws for `ids` this week: marginals and correlations measured in this league."""
    base = _read("proj_baseline", store.DATA_DIR, area="derived").filter(
        (pl.col("league_id") == data.league_id) & (pl.col("week") == week) & pl.col("is_future")
    )
    base = base.with_columns(
        role=pl.col("position")
        + pl.col("projection")
        .rank("ordinal", descending=True)
        .over("team", "position")
        .cast(pl.String)
    )
    info = {r["gsis_id"]: (r["team"], r["role"]) for r in base.iter_rows(named=True)}
    teams = tuple(info.get(i, ("", ""))[0] or "" for i in ids)
    roles = tuple(info.get(i, ("", ""))[1] for i in ids)
    slate = Slate(
        tuple(ids),
        tuple(positions[i] for i in ids),
        teams,
        roles,
        tuple(values.get(i, 0.0) for i in ids),
    )

    pairs = _read("correlation_pairs", store.DATA_DIR, area="derived").filter(
        pl.col("league_id") == data.league_id
    )
    rho: dict[str, dict[tuple[str, str], float]] = {"same_team": {}, "opposing": {}}
    for relation, a, b, r in pairs.select("relation", "role_a", "role_b", "rho").iter_rows():
        rho[relation][(a, b)] = rho[relation][(b, a)] = r
    schedule = _read("nfl_schedules", store.DATA_DIR).filter(
        (pl.col("season") == load_config().season) & (pl.col("week") == week)
    )
    opponent_of = {
        **dict(zip(schedule["home_team"], schedule["away_team"], strict=True)),
        **dict(zip(schedule["away_team"], schedule["home_team"], strict=True)),
    }
    marginals = _read("marginals", store.DATA_DIR, area="derived").filter(
        pl.col("league_id") == data.league_id
    )
    ratios = {
        position: g.sort("tau")["ratio"].to_numpy()
        for (position,), g in marginals.group_by("position")
    }
    assert all(len(r) == len(LEVELS) for r in ratios.values())
    corr = correlation_matrix(slate, rho["same_team"], rho["opposing"], opponent_of)
    return sample_points(slate, corr, ratios, n_sims, LINEUP_SEED)


def _constant_points(data: LeagueData, n_sims: int, seed: int) -> np.ndarray:
    """K and DEF slots: each is a league-average draw (their points are not projected yet)."""
    from fantasy.sim.lineup import constant_slot_count

    counts = constant_slot_count(data.roster_positions)
    mean = counts.get("K", 0) * data.k_mean + counts.get("DEF", 0) * data.def_mean
    var = counts.get("K", 0) * data.k_var + counts.get("DEF", 0) * data.def_var
    return mean + np.sqrt(var) * np.random.default_rng(seed).standard_normal(n_sims)
