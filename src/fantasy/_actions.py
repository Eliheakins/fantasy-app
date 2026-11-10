"""Streaming candidates and the This week action list."""

from pathlib import Path

import polars as pl

from fantasy._engine import _league, _names, _read
from fantasy._leagues import my_league
from fantasy._lineup import lineup, win_probability
from fantasy._market import waivers
from fantasy._schemas import ENGINE_SCHEMAS, empty
from fantasy.teams import TEAM_MAP

STREAM_WEEKS = 3


def streamers(
    league_key: str,
    kind: str,
    top_n: int = 8,
    data_dir: Path | None = None,
    team: int | None = None,
) -> pl.DataFrame:
    """Best free K or DEF over the next weeks, plus mine for comparison. kind is "K" or "DEF"."""
    me = my_league(league_key, data_dir, team)
    if me is None or kind not in ("K", "DEF"):
        return empty("streamers")
    lid, current, mine = me["league_id"], int(me["current_week"]), me["roster_id"]
    proj = (
        _read("streaming_projection", data_dir, area="derived")
        .filter((pl.col("league_id") == lid) & (pl.col("kind") == kind))
        .filter(pl.col("week") < current + STREAM_WEEKS)
    )
    rostered = _read("rosters", data_dir).filter(pl.col("league_id") == lid)
    players = _read("sleeper_players", data_dir).select("sleeper_id", "full_name", "position")
    if kind == "DEF":
        owned = rostered.join(players, on="sleeper_id").filter(pl.col("position") == "DEF")
        owned = owned.with_columns(
            pl.col("sleeper_id")
            .replace_strict(TEAM_MAP, default=pl.col("sleeper_id"))
            .alias("unit")
        )
        name = {u: f"{u} D/ST" for u in proj["unit"].unique()}
    else:
        id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
        owned = rostered.join(id_map, on="sleeper_id").join(players, on="sleeper_id")
        owned = owned.filter(pl.col("position") == "K").rename({"gsis_id": "unit"})
        name = _names(data_dir)
    mine_units = set(owned.filter(pl.col("roster_id") == mine)["unit"])
    taken_units = set(owned["unit"]) - mine_units
    totals = proj.group_by("unit", "team").agg(
        pl.col("projection").filter(pl.col("week") == current).sum().alias("this_week"),
        pl.col("projection").sum().alias("next_three"),
    )
    rows = totals.with_columns(
        pl.col("unit").replace_strict(name, default=pl.col("unit")).alias("name"),
        pl.col("unit").is_in(list(mine_units)).alias("is_mine"),
    )
    free = rows.filter(~pl.col("unit").is_in(list(taken_units | mine_units)))
    keep = pl.concat(
        [rows.filter(pl.col("is_mine")), free.sort("next_three", descending=True).head(top_n)]
    )
    return keep.select(*ENGINE_SCHEMAS["streamers"]).sort("next_three", descending=True)


UNAVAILABLE = frozenset({"Out", "Doubtful", "IR", "PUP", "Sus", "NFI"})


LINEUP_GAP = 1.0  # expected points below the best lineup before the gap is worth a note


WAIVER_PLAYOFF_GAIN = 0.005  # playoff odds change that makes an add worth mentioning


def actions(
    league_key: str,
    n: int = 3,
    odds: pl.DataFrame | None = None,
    adds: pl.DataFrame | None = None,
    data_dir: Path | None = None,
    team: int | None = None,
) -> pl.DataFrame:
    """The most useful things to do now, most urgent first: kind and text.

    Order: injured or out players in your lineup, a lineup change, then a waiver add. `odds` is a
    `win_probability` result to reuse; `adds` a `waivers`-shaped frame (see `stored_adds`) that
    skips the waiver re-simulation.
    """
    loaded = _league(league_key, data_dir, team)
    rows = lineup(league_key, loaded=loaded, data_dir=data_dir, team=team)
    found: list[tuple[str, str]] = []
    if not rows.is_empty():
        found.extend(
            ("Injury", f"{r['full_name']} is {r['injury']} and in your lineup")
            for r in rows.filter(pl.col("starting_now") & ~pl.col("locked")).iter_rows(named=True)
            if r["injury"] in UNAVAILABLE
        )
        known = bool(rows["starting_now"].any())
        gap = float(
            rows.filter(pl.col("recommended"))["projection"].to_numpy().sum()
            - rows.filter(pl.col("starting_now"))["projection"].to_numpy().sum()
        )
        by_name = rows["full_name"]
        if known and gap >= LINEUP_GAP:
            start = by_name.filter(rows["recommended"] & ~rows["starting_now"]).to_list()
            sit = by_name.filter(rows["starting_now"] & ~rows["recommended"]).to_list()
            found.append(
                ("Lineup", f"Start {', '.join(start)} over {', '.join(sit)} (+{gap:.1f} points)")
            )
    if odds is None:
        odds = win_probability(league_key, loaded=loaded, data_dir=data_dir, team=team)
    if not odds.is_empty():
        by_option = {r["option"]: r for r in odds.iter_rows(named=True)}
        pick, best = by_option["win_prob"], by_option["max_points"]
        if pick["tag"] != "same as max points":
            names = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
            ins = [names[i] for i in set(pick["gsis_ids"]) - set(best["gsis_ids"])]
            out = [names[i] for i in set(best["gsis_ids"]) - set(pick["gsis_ids"])]
            found.append(
                (
                    "Win probability",
                    f"{pick['tag'].capitalize()}: start {', '.join(ins)} over {', '.join(out)} "
                    f"({pick['win_prob']:.1%} vs {best['win_prob']:.1%} to win)",
                )
            )
    if adds is None:
        adds = waivers(league_key, loaded=loaded, data_dir=data_dir, team=team)
    if not adds.is_empty():
        top = adds.sort("playoff_delta", descending=True).row(0, named=True)
        if top["playoff_delta"] >= WAIVER_PLAYOFF_GAIN:
            found.append(
                (
                    "Waiver",
                    f"Add {top['full_name']}, drop {top['drop_name']}: "
                    f"{top['playoff_delta']:+.1%} playoff odds, {top['delta_points']:+.1f} points",
                )
            )
    return pl.DataFrame(found[:n], schema={"kind": pl.String, "text": pl.String}, orient="row")
