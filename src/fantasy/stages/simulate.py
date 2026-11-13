"""Simulate the rest of each league's season and write playoff and title odds.

Writes sim_season and sim_bracket (latest) and appends to sim_season_history (one row per team
per run, so the
Outlook chart can show odds over time). Odds assume current rosters: no waiver moves, trades or
injuries beyond the spread already in each player's outcome distribution.

Run: uv run python -m fantasy.stages.simulate [--no-archive]   (no history row: the Sleeper refresh)
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from fantasy import store
from fantasy._runs import note_soft_failure
from fantasy.auth import leagues
from fantasy.config import load_config
from fantasy.scoring import UnmappedScoring, check_keys
from fantasy.sim.bracket import row_problem
from fantasy.sim.league_data import load_league_data
from fantasy.sim.lineup import UnknownSlot
from fantasy.sim.odds import LeagueData, build_inputs
from fantasy.sim.season import (
    SeasonInputs,
    conditional_odds,
    simulate_season,
    team_scores,
    win_need_odds,
)


def append_history(latest: pl.DataFrame, data_dir: Path | None = None) -> pl.DataFrame:
    """Append this run to the archive table, which is never overwritten, only extended."""
    stamped = latest.with_columns(
        pl.lit(datetime.now(UTC).isoformat(timespec="seconds")).alias("run_at")
    ).select(*store.SCHEMAS["sim_season_history"])
    stamped = store.with_archive("sim_season_history", stamped, data_dir)
    store.write_table("sim_season_history", stamped, "archive", data_dir)
    return stamped


def team_week_rows(data: LeagueData, inp: SeasonInputs) -> list[tuple[Any, ...]]:
    """(league_id, roster_id, week, as_of_week, exp_points, sd_points) for each remaining
    regular-season week. exp_points counts the persistent shift (absence losses sit in it)."""
    expected = inp.mean + inp.shift.mean(axis=2)
    spread = np.sqrt(inp.noise_sd**2 + inp.shift.var(axis=2))
    return [
        (data.league_id, rid, week, data.current_week, float(expected[t, w]), float(spread[t, w]))
        for t, rid in enumerate(data.roster_ids)
        for w, week in enumerate(inp.weeks)
        if week < data.playoff_start
    ]


def _inputs(
    league: dict[str, Any], n_sims: int, data_dir: Path | None
) -> tuple[LeagueData, SeasonInputs] | None:
    """The league's data and simulation inputs. A league someone added that the app cannot model
    (scoring it does not map, a lineup slot it does not know) is marked and left out, and its
    unprojected players only warn; the same failure in a config.toml league stops the run."""
    added = not leagues.is_configured(league["league_id"])
    try:
        if added:  # score drops such a league too; check here so the two stages agree
            check_keys(json.loads(league["scoring_settings"]))
        data = load_league_data(league, strict=not added, data_dir=data_dir)
        return data, build_inputs(data, None, n_sims, 0)
    except (UnmappedScoring, UnknownSlot) as err:
        if not added:
            raise
        leagues.skip_added(league["league_id"], league["league_key"], "simulate", err, data_dir)
        return None


def _tag(frame: pl.DataFrame, league_id: str, data: LeagueData) -> pl.DataFrame:
    """Add the league id and the week the odds were computed as of."""
    return frame.with_columns(
        pl.lit(league_id).alias("league_id"),
        pl.lit(data.current_week).cast(pl.Int64).alias("as_of_week"),
    )


def run(
    n_sims: int | None = None, archive: bool = True, data_dir: Path | None = None
) -> pl.DataFrame:
    """Simulate every league. `archive=False` skips the append-only history (live ticks)."""
    cfg = load_config()
    n_sims = n_sims or cfg.n_sims
    rows, seed_rows, bracket_rows, week_rows, conditional, win_need = [], [], [], [], [], []
    for league in store.read_table("leagues", "raw", data_dir).iter_rows(named=True):
        problem = row_problem(league)
        if problem:  # a league the bracket model does not fit is left out, not a crash for everyone
            note_soft_failure(f"simulate left out {league['league_key']}: {problem}")
            continue
        built = _inputs(league, n_sims, data_dir)
        if built is None:
            continue
        data, inp = built
        started = data.current_week >= data.playoff_start
        if started and not any(m.bracket == "winners" for m in data.bracket):
            note_soft_failure(
                f"simulate {league['league_key']}: playoffs started but no bracket rows; "
                "title odds use a guessed bracket"
            )
        result = simulate_season(inp)
        week_rows += team_week_rows(data, inp)
        scores = team_scores(inp)  # one draw for both display tables below
        cond = _tag(conditional_odds(inp, result, scores), league["league_id"], data)
        conditional.append(cond.select(*store.SCHEMAS["sim_conditional"]))
        need = _tag(win_need_odds(inp, result, scores=scores), league["league_id"], data)
        win_need.append(need.select(*store.SCHEMAS["sim_win_need"]))
        bracket_rows += [
            (
                league["league_id"],
                roster_id,
                rnd,
                float(result.p_reach[j, i]),
                float(result.p_win[j, i]),
            )
            for i, roster_id in enumerate(data.roster_ids)
            for j, rnd in enumerate(result.rounds)
            if result.p_reach[j, i] > 0
        ]
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
    # one call so the tables cannot drift from sim_season; the append-only history goes last:
    # a failure earlier leaves it behind the tables, never ahead
    store.write_tables(
        {
            "sim_bracket": pl.DataFrame(
                bracket_rows, schema=store.SCHEMAS["sim_bracket"], orient="row"
            ),
            "sim_seeds": pl.DataFrame(seed_rows, schema=store.SCHEMAS["sim_seeds"], orient="row"),
            "sim_team_weeks": pl.DataFrame(
                week_rows, schema=store.SCHEMAS["sim_team_weeks"], orient="row"
            ),
            "sim_conditional": pl.concat(conditional)
            if conditional
            else pl.DataFrame(schema=store.SCHEMAS["sim_conditional"]),
            "sim_win_need": pl.concat(win_need)
            if win_need
            else pl.DataFrame(schema=store.SCHEMAS["sim_win_need"]),
            "sim_season": latest,
        },
        data_dir=data_dir,
    )
    if archive:
        append_history(latest, data_dir)
    return latest


def main() -> None:
    latest = run(archive="--no-archive" not in sys.argv[1:])
    league_keys = store.read_table("leagues", "raw").select("league_id", "league_key")
    pl.Config.set_tbl_rows(30)
    shown = latest.join(league_keys, on="league_id").sort(
        ["league_key", "p_title"], descending=[False, True]
    )
    print(shown.select("league_key", "team_name", "p_playoffs", "p_bye", "p_title", "exp_wins"))


if __name__ == "__main__":
    main()
