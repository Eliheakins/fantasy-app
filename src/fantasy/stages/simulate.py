"""Simulate the rest of each league's season and write playoff and title odds.

Writes sim_season (latest) and appends to sim_season_history (one row per team per run, so the
Outlook chart can show odds over time). Odds assume current rosters: no waiver moves, trades or
injuries beyond the spread already in each player's outcome distribution.

Run: uv run python -m fantasy.stages.simulate
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim.availability import scale_projections
from fantasy.sim.lineup import Player
from fantasy.sim.odds import CurrentWeek, LeagueData, league_odds
from fantasy.sim.schedule import pairings, standings

SKILL = ["QB", "RB", "WR", "TE"]
K_HISTORY_FROM = 2023
DEF_MEAN, DEF_VAR = 8.0, 25.0  # fallback when too few starting defenses have scored
MIN_DEF_ROWS = 20  # otherwise use the league's own starting-defense scores (until E3-7)


def current_state(
    mp: pl.DataFrame, projections: dict[str, float], week_pool: dict[str, str]
) -> dict[int, CurrentWeek]:
    """Per roster: realized points of set starters, and the starters still to score.

    mp: this week's matchup_players for one league joined to position and gsis_id.
    week_pool maps gsis_id to position for players that have a projection this week.
    """
    out = {}
    for (roster_id,), g in mp.filter(pl.col("is_starter")).group_by("roster_id"):
        scored = g.filter(pl.col("points") > 0)
        waiting = g.filter(pl.col("points").is_null() | (pl.col("points") <= 0))
        players = tuple(
            Player(r["gsis_id"], r["position"], projections[r["gsis_id"]])
            for r in waiting.iter_rows(named=True)
            if r["position"] in SKILL and r["gsis_id"] in projections and r["gsis_id"] in week_pool
        )
        out[int(roster_id)] = CurrentWeek(
            realized=float(scored["points"].sum() or 0.0),
            open_players=players,
            open_k=waiting.filter(pl.col("position") == "K").height,
            open_def=waiting.filter(pl.col("position") == "DEF").height,
        )
    return out


def load_league_data(league: dict[str, Any]) -> LeagueData:
    lid, current = league["league_id"], int(league["current_week"])
    playoff_start = int(league["playoff_week_start"])
    teams = store.read_table("league_teams", "raw").filter(pl.col("league_id") == lid)
    matchups = store.read_table("matchups", "raw").filter(pl.col("league_id") == lid)
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id")
    players = store.read_table("sleeper_players", "raw").select("sleeper_id", "position")

    base = standings(matchups, current - 1)
    wins0 = dict(zip(base["roster_id"], base["wins"] + 0.5 * base["ties"], strict=True))
    points0 = dict(zip(base["roster_id"], base["points_for"], strict=True))
    roster_ids = sorted(teams["roster_id"].to_list())

    rosters = (
        store.read_table("rosters", "raw")
        .filter(pl.col("league_id") == lid)
        .join(id_map, on="sleeper_id")
        .join(players, on="sleeper_id")
        .filter(pl.col("gsis_id").is_not_null() & pl.col("position").is_in(SKILL))
        .select("roster_id", "gsis_id", "position")
        .unique()
    )
    future = store.read_table("proj_baseline").filter(
        (pl.col("league_id") == lid) & pl.col("is_future") & (pl.col("week") >= current)
    )
    flagged = (
        store.read_table("sleeper_players", "raw")
        .select("sleeper_id", "injury_status")
        .filter(pl.col("injury_status").is_not_null())
        .join(id_map, on="sleeper_id")
        .filter(pl.col("gsis_id").is_not_null())
    )
    projections = scale_projections(
        future.select("gsis_id", "week", "projection"),
        dict(zip(flagged["gsis_id"], flagged["injury_status"], strict=True)),
        current,
    )
    active = (
        store.read_table("sleeper_players", "raw")
        .filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position").is_in(SKILL))
        .join(id_map, on="sleeper_id")
        .filter(pl.col("gsis_id_right").is_not_null())
    )
    positions = dict(zip(active["gsis_id_right"], active["position"], strict=True))
    marginals = store.read_table("marginals").filter(pl.col("league_id") == lid)
    cv = dict(marginals.select("position", "cv").unique().iter_rows())
    same_team = store.read_table("correlation_pairs").filter(
        (pl.col("league_id") == lid) & (pl.col("relation") == "same_team")
    )
    rho: dict[tuple[str, str], float] = {}
    for a, b, r in same_team.select("role_a", "role_b", "rho").iter_rows():
        rho[(a, b)] = rho[(b, a)] = r

    kicker = store.read_table("player_points").filter(
        (pl.col("league_id") == lid)
        & (pl.col("position") == "K")
        & (pl.col("season") >= K_HISTORY_FROM)
    )
    k_points = kicker["points"].to_numpy()
    def_done = (
        store.read_table("matchup_players", "raw")
        .filter((pl.col("league_id") == lid) & (pl.col("week") < current) & pl.col("is_starter"))
        .join(players, on="sleeper_id")
        .filter((pl.col("position") == "DEF") & pl.col("points").is_not_null())
    )
    def_points = def_done["points"].to_numpy()
    enough = def_points.size >= MIN_DEF_ROWS
    mp = (
        store.read_table("matchup_players", "raw")
        .filter((pl.col("league_id") == lid) & (pl.col("week") == current))
        .join(players, on="sleeper_id")
        .join(id_map, on="sleeper_id", how="left")
    )
    this_week = projections.filter(pl.col("week") == current)
    week_projection = dict(zip(this_week["gsis_id"], this_week["projection"], strict=True))
    week_pool = dict(zip(rosters["gsis_id"], rosters["position"], strict=True))
    week_pool.update({g: "" for g in week_projection})

    return LeagueData(
        roster_ids=roster_ids,
        team_names=dict(zip(teams["roster_id"], teams["team_name"], strict=True)),
        current_week=current,
        playoff_start=playoff_start,
        roster_positions=list(league["roster_positions"]),
        rosters=rosters,
        projections=projections,
        cv=cv,
        pair_rho=rho,
        pairings={
            week: [(int(a), int(b)) for a, b in g.select("roster_a", "roster_b").iter_rows()]
            for (week,), g in pairings(matchups).group_by("week")
        },
        wins0={int(k): float(v) for k, v in wins0.items()},
        points0={int(k): float(v) for k, v in points0.items()},
        k_mean=float(k_points.mean()) if k_points.size else 0.0,
        k_var=float(k_points.var(ddof=1)) if k_points.size > 1 else 0.0,
        def_mean=float(def_points.mean()) if enough else DEF_MEAN,
        def_var=float(def_points.var(ddof=1)) if enough else DEF_VAR,
        current=current_state(mp, week_projection, week_pool),
        positions=positions,
        trade_deadline=int(league["trade_deadline"] or 99),
        league_id=lid,
    )


def append_history(latest: pl.DataFrame, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Append this run to the archive table, which is never overwritten, only extended."""
    stamped = latest.with_columns(
        pl.lit(datetime.now(UTC).isoformat(timespec="seconds")).alias("run_at")
    ).select(*store.SCHEMAS["sim_season_history"])
    try:
        old = store.read_table("sim_season_history", "archive", data_dir)
        stamped = pl.concat([old, stamped])
    except FileNotFoundError:
        pass
    store.write_table("sim_season_history", stamped, "archive", data_dir)
    return stamped


def run(n_sims: int | None = None) -> pl.DataFrame:
    cfg = load_config()
    n_sims = n_sims or cfg.n_sims
    rows, seed_rows = [], []
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        data = load_league_data(league)
        result, _ = league_odds(data, n_sims=n_sims)
        for i, roster_id in enumerate(data.roster_ids):
            seed_rows += [
                (league["league_id"], roster_id, k + 1, float(result.p_seed[i, k]))
                for k in range(len(data.roster_ids))
            ]
            rows.append(
                {
                    "league_id": league["league_id"],
                    "team_name": data.team_names[roster_id],
                    "roster_id": roster_id,
                    "as_of_week": data.current_week,
                    "n_sims": n_sims,
                    "p_playoffs": float(result.p_playoffs[i]),
                    "p_bye": float(result.p_bye[i]),
                    "p_title": float(result.p_title[i]),
                    "exp_wins": float(result.exp_wins[i]),
                }
            )
    latest = pl.DataFrame(rows, schema=store.SCHEMAS["sim_season"])
    store.write_table("sim_season", latest)
    store.write_table(
        "sim_seeds", pl.DataFrame(seed_rows, schema=store.SCHEMAS["sim_seeds"], orient="row")
    )
    append_history(latest)
    return latest


def main() -> None:
    latest = run()
    leagues = store.read_table("leagues", "raw").select("league_id", "league_key")
    pl.Config.set_tbl_rows(30)
    shown = latest.join(leagues, on="league_id").sort(
        ["league_key", "p_title"], descending=[False, True]
    )
    print(shown.select("league_key", "team_name", "p_playoffs", "p_bye", "p_title", "exp_wins"))


if __name__ == "__main__":
    main()
