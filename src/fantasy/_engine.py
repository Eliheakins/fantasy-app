"""Engine internals behind data_api: shared table reads, joint draws and injury notes.

Nothing here calls `data_api.leagues`, so the patch seams tests use on `data_api` are not bypassed.
Tables read here are required: a missing one raises FileNotFoundError.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.availability import LONG_TERM, locked_teams
from fantasy.sim.calibration import tier_of
from fantasy.sim.lineup import Player, auto_lineup, constant_slot_count
from fantasy.sim.odds import CurrentWeek, LeagueData
from fantasy.sim.sampler import LEVELS, Slate, correlation_matrix, sample_points

PLAY_PROB_FLOOR = 1e-9  # guards the division by a chance of playing
LINEUP_SEED = 11
KD_SEED_OFFSET = 1000  # K and DEF draws are independent of the player draws


def _read(name: str, data_dir: Path, area: str = "raw") -> pl.DataFrame:
    """An optional table, or an empty frame with its columns if no stage has written it yet.

    Core tables go through `store.read_table` directly so that a missing one raises."""
    try:
        return store.read_table(name, area, data_dir)
    except FileNotFoundError:
        return pl.DataFrame(schema=store.SCHEMAS[name])


def _league(league_key: str) -> tuple[LeagueData, int]:
    """Simulation inputs for one league and my roster id."""
    from fantasy.stages.simulate import load_league_data  # heavy imports, only when asked

    row = store.read_table("leagues", "raw").filter(pl.col("league_key") == league_key)
    if row.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    league = row.row(0, named=True)
    teams = store.read_table("league_teams", "raw")
    mine = teams.filter((pl.col("league_id") == league["league_id"]) & pl.col("is_me"))
    if mine.is_empty():
        raise ValueError(
            f"no team is marked is_me in league {league_key!r}; set user_id in config.toml "
            "and run `make refresh`"
        )
    return load_league_data(league, strict=False), int(mine["roster_id"][0])


def _id_map(*extra: str) -> pl.DataFrame:
    """Sleeper to nflverse ids, plus any other `id_map` columns asked for."""
    return store.read_table("id_map", "derived").select("sleeper_id", "gsis_id", *extra)


def _gsis_players(player_column: str, *id_columns: str) -> pl.DataFrame:
    """Players with an nflverse id: gsis_id, any extra `id_map` columns, and `player_column`."""
    players = store.read_table("sleeper_players", "raw").select("sleeper_id", player_column)
    return (
        _id_map(*id_columns).join(players, on="sleeper_id").filter(pl.col("gsis_id").is_not_null())
    )


def _names() -> dict[str, str]:
    """nflverse ID -> player name."""
    joined = _gsis_players("full_name")
    return dict(zip(joined["gsis_id"], joined["full_name"], strict=True))


def _set_starters(league_id: str, week: int, roster_id: int) -> list[str]:
    """nflverse ids of the players a team has set as starters in Sleeper for a week."""
    return (
        store.read_table("matchup_players", "raw")
        .filter(
            (pl.col("league_id") == league_id)
            & (pl.col("week") == week)
            & (pl.col("roster_id") == roster_id)
            & pl.col("is_starter")
        )
        .join(_id_map(), on="sleeper_id")["gsis_id"]
        .to_list()
    )


def _marginals(league_id: str) -> pl.DataFrame:
    return store.read_table("marginals", "derived").filter(pl.col("league_id") == league_id)


def _pool(
    data: LeagueData, roster_id: int, positions: dict[str, str], values: dict[str, float]
) -> list[Player]:
    """A team's players with a projection this week."""
    return [
        Player(i, positions[i], values[i]) for i in moves.team_ids(data, roster_id) if i in values
    ]


def _opponent_of(data: LeagueData, mine: int, week: int) -> int | None:
    """The roster id I play in `week`, if any."""
    return next(
        (b if a == mine else a for a, b in data.pairings.get(week, []) if mine in (a, b)), None
    )


def _tier_edges(marginals: pl.DataFrame) -> dict[str, list[float]]:
    """Per position, the upper projection edges of tiers 0 and 1 (tier 2 is everything above)."""
    rows = marginals.filter(pl.col("tier").is_in([0, 1])).select("position", "tier", "proj_max")
    out: dict[str, dict[int, float]] = {}
    for position, tier, upper in rows.unique().iter_rows():
        out.setdefault(position, {})[tier] = upper
    return {p: [t[0], t[1]] for p, t in out.items() if len(t) == 2}


def _tier(edges: dict[str, list[float]], player: Player) -> int:
    """The marginal tier of a player's projection, or the all-tier shape (-1) if unknown."""
    return tier_of(edges[player.position], player.value) if player.position in edges else -1


def _injury_note(data: LeagueData, gsis_id: str) -> str | None:
    """Injury, body part and the chance of playing this game and the next, for a flagged player."""
    flag = data.injuries.get(gsis_id)
    if flag is None or not flag[0]:
        return None
    status, body, _ = flag
    text = status + (f" ({body.lower()})" if body else "")
    if status in LONG_TERM or "play_prob" not in data.projections.columns:
        return text + (", out at least 4 games" if status in LONG_TERM else "")
    rows = data.projections.filter(pl.col("gsis_id") == gsis_id).sort("week").head(2)
    chances = rows["play_prob"].to_list()
    if not chances:
        return text
    return (
        text
        + f": {chances[0]:.0%} to play"
        + (f", {chances[1]:.0%} next game" if len(chances) > 1 else "")
    )


def _status_and_locks(
    week: int, current_week: int, now: datetime | None = None
) -> tuple[dict[str, str], set[str]]:
    """Injury status by nflverse ID, and ids whose game has started (current week only)."""
    joined = _gsis_players("injury_status", "nfl_team")
    status = {g: s for g, s in zip(joined["gsis_id"], joined["injury_status"], strict=True) if s}
    if week != current_week:
        return status, set()
    started = locked_teams(
        store.read_table("nfl_schedules", "raw"),
        load_config().season,
        week,
        now or datetime.now(UTC),
    )
    locked = set(joined.filter(pl.col("nfl_team").is_in(started))["gsis_id"].to_list())
    return status, locked


def _play_probs(data: LeagueData, week: int) -> dict[str, float]:
    """Each projected player's chance of playing in `week` (1.0 where not recorded)."""
    if "play_prob" not in data.projections.columns:
        return {}
    rows = data.projections.filter(pl.col("week") == week)
    return dict(zip(rows["gsis_id"], rows["play_prob"], strict=True))


def _constant_points(
    data: LeagueData, n_sims: int, seed: int, state: CurrentWeek | None = None
) -> np.ndarray:
    """K and DEF slots: points already scored plus a league-average draw for what is left
    (their points are not projected yet). `state` is None for a week not yet under way."""
    counts = constant_slot_count(data.roster_positions)
    open_k = counts.get("K", 0) if state is None else state.open_k
    open_def = counts.get("DEF", 0) if state is None else state.open_def
    scored = 0.0 if state is None else state.kd_actual
    mean = scored + open_k * data.k_mean + open_def * data.def_mean
    var = open_k * data.k_var + open_def * data.def_var
    return mean + np.sqrt(var) * np.random.default_rng(seed).standard_normal(n_sims)


def _opponent_lineup(
    data: LeagueData,
    opp: int,
    week: int,
    positions: dict[str, str],
    values: dict[str, float],
    slots: list[str],
) -> list[str]:
    """Skill players the opponent starts: set in Sleeper if known, else their best lineup."""
    known = [i for i in _set_starters(data.league_id, week, opp) if i in positions]
    if week == data.current_week and known:
        return known
    return sorted(auto_lineup(_pool(data, opp, positions, values), slots).players)


def _draw_points(
    data: LeagueData,
    ids: list[str],
    positions: dict[str, str],
    values: dict[str, float],
    plays: dict[str, float],
    tier_means: dict[str, float],
    week: int,
    n_sims: int,
) -> np.ndarray:
    """Joint draws for `ids` this week: marginals and correlations measured in this league.
    `values` are expected points, `plays` each player's chance of playing, and `tier_means` his
    full-game points when he plays, which picks the floor-and-ceiling shape his size has."""
    base = store.read_table(store.projection_name(), "derived").filter(
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
        tuple(plays.get(i, 1.0) for i in ids),
    )

    pairs = store.read_table("correlation_pairs", "derived").filter(
        pl.col("league_id") == data.league_id
    )
    rho: dict[str, dict[tuple[str, str], float]] = {"same_team": {}, "opposing": {}}
    for relation, a, b, r in pairs.select("relation", "role_a", "role_b", "rho").iter_rows():
        rho[relation][(a, b)] = rho[relation][(b, a)] = r
    schedule = store.read_table("nfl_schedules", "raw").filter(
        (pl.col("season") == load_config().season) & (pl.col("week") == week)
    )
    opponent_of = {
        **dict(zip(schedule["home_team"], schedule["away_team"], strict=True)),
        **dict(zip(schedule["away_team"], schedule["home_team"], strict=True)),
    }
    marginals = _marginals(data.league_id)
    ratios = {
        (position if tier < 0 else f"{position}:{tier}"): g.sort("tau")["ratio"].to_numpy()
        for (position, tier), g in marginals.group_by("position", "tier")
    }
    if any(len(r) != len(LEVELS) for r in ratios.values()):
        raise ValueError("marginals do not have one ratio per quantile level; rerun distributions")
    missing = {positions[i] for i in ids} - {k for k in ratios if ":" not in k}
    if missing:  # the sampler falls back to the all-tier shape for a position
        raise ValueError(f"marginals have no shape for {sorted(missing)}; rerun distributions")
    edges = _tier_edges(marginals)
    tiers = tuple(
        tier_of(edges[positions[i]], tier_means.get(i, 0.0)) if positions[i] in edges else -1
        for i in ids
    )
    slate = replace(slate, tiers=tiers)
    corr = correlation_matrix(slate, rho["same_team"], rho["opposing"], opponent_of)
    return sample_points(slate, corr, ratios, n_sims, LINEUP_SEED)


def _week_points(
    data: LeagueData,
    ids: list[str],
    positions: dict[str, str],
    values: dict[str, float],
    week: int,
    n_sims: int,
) -> tuple[np.ndarray, dict[str, int]]:
    """Joint points draws for `ids` in `week` (live points added in the current week), and each
    id's column in the draws."""
    live = data.live if week == data.current_week else {}
    share = np.array([live.get(i, (0.0, 1.0))[1] for i in ids])
    actual = np.array(
        [live.get(i, (0.0, 1.0))[0] if share[k] < 1.0 else 0.0 for k, i in enumerate(ids)]
    )
    chance = _play_probs(data, week)
    plays = {i: (1.0 if share[k] < 1.0 else chance.get(i, 1.0)) for k, i in enumerate(ids)}
    tier_means = {i: values.get(i, 0.0) / max(chance.get(i, 1.0), PLAY_PROB_FLOOR) for i in ids}
    # a player whose game has started is playing, so what is left is his full-game points
    scaled = {
        i: (tier_means[i] if share[k] < 1.0 else values.get(i, 0.0)) * share[k]
        for k, i in enumerate(ids)
    }
    drawn = _draw_points(data, ids, positions, scaled, plays, tier_means, week, n_sims)
    return drawn + actual, {i: j for j, i in enumerate(ids)}


def _slots_of(
    chosen: frozenset[str], mean_of: dict[str, float], positions: dict[str, str], slots: list[str]
) -> list[str]:
    """The slot each chosen player fills (in sorted id order) when the lineup is set best."""
    lineup = auto_lineup([Player(i, positions[i], mean_of[i]) for i in chosen], slots)
    slot_by_id = {pid: slot for slot, pid in lineup.slots}
    return [slot_by_id[i] for i in sorted(chosen)]
