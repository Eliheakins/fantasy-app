"""Measure what an injury report implies: the chance of playing in each of the next four games,
and how well a player does when he plays through it.

For every skill player-week with a game status of Out, Doubtful or Questionable (nflverse injury
reports, 2018 to 2025), find whether he played in that game and the next three of his team's
games, and the ratio of his points to his baseline projection when he did play. Cells are by
status, practice participation (Questionable only) and injury type, each shrunk toward its
parent cell so thin cells (a rare injury type) borrow from the common case.

Run: uv run python -m fantasy.stages.injuries
"""

from typing import NamedTuple

import polars as pl

from fantasy import store
from fantasy.sim.scoring_scale import reference_league
from fantasy.stages import stat_line
from fantasy.stages.distributions import calibrated
from fantasy.stages.stat_line import stored as stat_line_table
from fantasy.store import SKILL

HORIZON = 4
SHRINK = 30.0  # pseudo-observations pulling a cell toward its parent
PERF_SHRINK = 40.0  # pseudo-games at a ratio of 1.0 for the play-through discount
MIN_PROJECTION = 3.0  # baseline projections below this give unstable point ratios
STATUSES = ("Out", "Doubtful", "Questionable")
BODIES = (
    "Hamstring",
    "Ankle",
    "Knee",
    "Concussion",
    "Shoulder",
    "Foot",
    "Groin",
    "Hip",
    "Calf",
    "Quadricep",
    "Back",
    "Illness",
)
PRACTICE = {
    "Did Not Participate In Practice": "DNP",
    "Limited Participation in Practice": "Limited",
    "Full Participation in Practice": "Full",
}
ANY = "any"
OTHER = "Other"


class Cell(NamedTuple):
    """Raw counts for one group of flagged player-weeks."""

    n: int
    seen: tuple[int, ...]  # per horizon game: rows where the game exists
    rate: tuple[float, ...]  # per horizon game: share who played
    played: int  # rows who played game 0 with a usable projection
    points: float
    projected: float


class Effect(NamedTuple):
    """A cell after shrinkage toward its parent."""

    n: int
    p: tuple[float, ...]
    perf: float


def build_panel(
    injuries: pl.DataFrame,
    stats: pl.DataFrame,
    team_games: pl.DataFrame,
    points: pl.DataFrame,
    baseline: pl.DataFrame,
) -> pl.DataFrame:
    """One row per flagged skill player-week with played flags p0..p3 (None when his team has no
    such game left in the season), points and projection for game 0, practice and body groups."""
    touches = (
        pl.col("attempts").fill_null(0)
        + pl.col("carries").fill_null(0)
        + pl.col("targets").fill_null(0)
    )
    played = stats.filter(pl.col("season_type") == "REG").select(
        pl.col("player_id").alias("gsis_id"), "season", "week", touches.alias("opp")
    )
    games = store.team_game_index(team_games)
    rows = (
        injuries.filter(
            pl.col("position").is_in(SKILL)
            & (pl.col("game_type") == "REG")
            & pl.col("report_status").is_in(list(STATUSES))
        )
        .with_columns(pl.coalesce("report_primary_injury", "practice_primary_injury").alias("body"))
        .join(games, on=["season", "week", "team"])
    )
    # relevant players only: someone with at least 5 touches or targets earlier that season
    first = (
        played.filter(pl.col("opp") >= 5)
        .group_by("gsis_id", "season")
        .agg(pl.col("week").min().alias("first_relevant"))
    )
    rows = rows.join(first, on=["gsis_id", "season"]).filter(
        pl.col("week") > pl.col("first_relevant")
    )
    for k in range(HORIZON):
        later = games.select(
            "season", "team", (pl.col("g") - k).alias("g"), pl.col("week").alias(f"wk{k}")
        )
        flag = played.select(
            "gsis_id", "season", pl.col("week").alias(f"wk{k}"), (pl.col("opp") > 0).alias(f"p{k}")
        )
        rows = rows.join(later, on=["season", "team", "g"], how="left").join(
            flag, on=["gsis_id", "season", f"wk{k}"], how="left"
        )
        rows = rows.with_columns(
            pl.when(pl.col(f"wk{k}").is_null())
            .then(None)
            .otherwise(pl.col(f"p{k}").fill_null(False))
            .alias(f"p{k}")
        )
    return (
        rows.join(points.rename({"week": "wk0"}), on=["gsis_id", "season", "wk0"], how="left")
        .join(baseline.rename({"week": "wk0"}), on=["gsis_id", "season", "wk0"], how="left")
        .with_columns(
            pl.col("practice_status").replace_strict(PRACTICE, default=None).alias("practice"),
            pl.when(pl.col("body").is_in(BODIES))
            .then(pl.col("body"))
            .otherwise(pl.lit(OTHER))
            .alias("body"),
        )
    )


def _cell(panel: pl.DataFrame) -> Cell:
    seen, rate = [], []
    for k in range(HORIZON):
        known = panel.filter(pl.col(f"p{k}").is_not_null())
        seen.append(known.height)
        # an empty cell's 0.0 has zero weight in shrink(); a root cell is fixed by its seen count
        rate.append(
            float(known[f"p{k}"].cast(pl.Float64).to_numpy().mean()) if known.height else 0.0
        )
    usable = panel.filter(
        pl.col("p0").fill_null(False)
        & (pl.col("proj") > MIN_PROJECTION)
        & pl.col("points").is_not_null()
    )
    return Cell(
        panel.height,
        tuple(seen),
        tuple(rate),
        usable.height,
        float(usable["points"].sum()) if usable.height else 0.0,
        float(usable["proj"].sum()) if usable.height else 0.0,
    )


def _fill_empty_horizons(cell: Cell) -> tuple[float, ...]:
    """A root cell with no rows at a horizon takes the previous horizon's rate (a game that
    exists for nobody carries no information); no rows at game 0 is a broken panel."""
    if cell.seen[0] == 0:
        raise ValueError("injury panel has no rows for a status: the panel is broken")
    out: list[float] = []
    for seen, rate in zip(cell.seen, cell.rate, strict=True):
        out.append(rate if seen else out[-1])
    return tuple(out)


def shrink(cell: Cell, parent: Effect | None) -> Effect:
    """A cell pulled toward its parent in proportion to how thin it is; the root keeps its own."""
    if parent is None:
        p = _fill_empty_horizons(cell)
    else:
        p = tuple(
            (seen * rate + SHRINK * up) / (seen + SHRINK)
            for seen, rate, up in zip(cell.seen, cell.rate, parent.p, strict=True)
        )
    perf = parent.perf if parent else 1.0
    if cell.played and cell.projected:
        mean_projection = cell.projected / cell.played
        own = (cell.points + PERF_SHRINK * mean_projection) / (
            cell.projected + PERF_SHRINK * mean_projection
        )
        weight = cell.played / (cell.played + SHRINK) if parent else 1.0
        perf = weight * own + (1 - weight) * (parent.perf if parent else 1.0)
    return Effect(cell.n, p, perf)


def estimate(panel: pl.DataFrame) -> pl.DataFrame:
    """The injury_effects table: status, practice, body, n, p0..p3, perf (see module doc)."""
    records = []

    def add(status: str, practice: str, body: str, effect: Effect) -> None:
        records.append(
            {
                "status": status,
                "practice": practice,
                "body": body,
                "n": effect.n,
                **{f"p{k}": effect.p[k] for k in range(HORIZON)},
                "perf": effect.perf,
            }
        )

    for status in STATUSES:
        in_status = panel.filter(pl.col("report_status") == status)
        if in_status.is_empty():  # no rows is no information, not "never plays": store no cells
            print(f"injuries: WARNING no panel rows for status {status}; no effects stored")
            continue
        status_effect = shrink(_cell(in_status), None)
        add(status, ANY, ANY, status_effect)
        practices = PRACTICE.values() if status == "Questionable" else ()
        for practice in (None, *practices):
            group = (
                in_status if practice is None else in_status.filter(pl.col("practice") == practice)
            )
            parent = status_effect if practice is None else shrink(_cell(group), status_effect)
            if practice is not None:
                add(status, practice, ANY, parent)
            for body in (*BODIES, OTHER):
                effect = shrink(_cell(group.filter(pl.col("body") == body)), parent)
                add(status, practice or ANY, body, effect)
    return pl.DataFrame(records, schema=store.SCHEMAS["injury_effects"])


def run() -> int:
    leagues = store.read_table("leagues", "raw")
    league_id = reference_league(leagues)  # point ratios only; the rest of the code uses this one
    season = int(leagues["season"].to_numpy().max())
    projection = calibrated(
        store.projection_table().filter(
            (pl.col("league_id") == league_id) & ~pl.col("is_future") & pl.col("has_history")
        )
    ).select("gsis_id", "season", "week", "projection")
    chance = stat_line_table()
    if chance is not None:  # perf is measured on games with touches or targets: against E, not qE
        projection = stat_line.scale(
            projection, chance.with_columns(1.0 / pl.col("q")), ["gsis_id", "season", "week"]
        )
    panel = build_panel(
        store.read_table("nfl_injuries", "raw").filter(pl.col("season") < season),
        store.read_table("nfl_player_stats", "raw"),
        store.read_table("team_games"),
        store.read_table("player_points")
        .filter(pl.col("league_id") == league_id)
        .select("gsis_id", "season", "week", "points"),
        projection.rename({"projection": "proj"}),
    )
    table = estimate(panel)
    store.write_table("injury_effects", table)
    return table.height


if __name__ == "__main__":
    print(f"{run()} rows")
