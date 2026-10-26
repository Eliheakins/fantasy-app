"""Turn an injury report into a chance of playing each of the next games, and a play-through
discount, using the table `stages/injuries.py` measures.

A flagged player gets a curve: the chance he plays in each of his team's next four games, then
healthy. Hamstrings, feet and ankles come back slower than groins and shoulders, and a
Questionable player who did not practice plays far less often than one who practiced in full.
While he plays through it his projection is discounted by a ratio that halves each week.

Long-term designations (IR, PUP and so on) keep the four-game minimum. Probable (and no
designation) counts as healthy. A status the table does not cover is treated as
Questionable, with a warning.
"""

import warnings
from collections.abc import Sequence

import polars as pl

from fantasy.sim.availability import HEALTHY_STATUSES, LONG_TERM, LONG_TERM_WEEKS
from fantasy.sim.blend import blend_all

Flag = tuple[str, str | None, str | None]  # report status, body part, practice participation
DECAY = 0.5  # the play-through discount keeps this share of itself each week


class InjuryModel:
    """Lookup over the injury_effects table with fallbacks from specific to general."""

    def __init__(self, effects: pl.DataFrame) -> None:
        self.cells = {
            (r["status"], r["practice"], r["body"]): (
                (r["p0"], r["p1"], r["p2"], r["p3"]),
                r["perf"],
            )
            for r in effects.iter_rows(named=True)
        }
        self.bodies = {body for _, _, body in self.cells}

    def curve(self, flag: Flag) -> tuple[tuple[float, ...], float] | None:
        """Chances of playing games 0 to 3 then healthy (1.0), and the play-through ratio.
        None when the status is not one the table covers."""
        status, body, practice = flag
        if status in LONG_TERM:
            return (0.0,) * LONG_TERM_WEEKS + (1.0,), 1.0
        group = body if body in self.bodies else "Other"
        for key in (
            (status, practice or "any", group),
            (status, practice or "any", "any"),
            (status, "any", group),
            (status, "any", "any"),
        ):
            if key in self.cells:
                probs, perf = self.cells[key]
                return (*probs, 1.0), perf
        return None


def _curve_or_questionable(
    model: InjuryModel, flag: Flag
) -> tuple[tuple[float, ...], float] | None:
    """The model's curve; a status it does not cover counts as Questionable (warned), except
    Probable, which is healthy (None)."""
    curve = model.curve(flag)
    if curve is not None or flag[0] in HEALTHY_STATUSES:
        return curve
    warnings.warn(f"unrecognised injury status {flag[0]!r}, treated as Questionable", stacklevel=2)
    return model.curve(("Questionable", flag[1], flag[2]))


def _steps(projections: pl.DataFrame, current_week: int) -> pl.DataFrame:
    """`projections` sorted, with `_k`: the player's game count from his first game of the
    current week on (0 is the next game), -1 for earlier weeks. Only his team's games count, so
    a bye week does not use up a step of a curve."""
    rows = projections.sort("gsis_id", "week").with_columns(
        pl.col("week").rank("ordinal").over("gsis_id").alias("_game")
    )
    ahead = rows.filter(pl.col("week") >= current_week)
    first = ahead.group_by("gsis_id").agg(pl.col("_game").min().alias("_first"))
    return (
        rows.join(first, on="gsis_id", how="left")
        .with_columns(
            pl.when(pl.col("week") >= current_week)
            .then(pl.col("_game") - pl.col("_first"))
            .otherwise(-1)
            .alias("_k")
        )
        .drop("_game", "_first")
    )


def _table_games(
    projections: pl.DataFrame,
    flagged: dict[str, Flag],
    model: InjuryModel | None,
    current_week: int,
    first_game_chance: dict[str, float] | None,
) -> set[tuple[str, int]]:
    """(gsis_id, week) of the games whose chance of playing `injury_projections` will take from
    the injury table: a flagged player's next games along his curve, except the first one when
    the classifier's chance replaces it. The curve's last entry ("healthy from then on") is not a
    measured chance."""
    if model is None:
        return set()
    override = first_game_chance or {}
    curves = {g: _curve_or_questionable(model, f) for g, f in flagged.items()}
    rows = _steps(projections, current_week)
    games = set()
    for gsis, week, k in zip(rows["gsis_id"], rows["week"], rows["_k"], strict=True):
        curve = curves.get(gsis)
        if curve is None or not 0 <= k < len(curve[0]) - 1 or (k == 0 and gsis in override):
            continue
        games.add((gsis, week))
    return games


def stat_line_blend(
    ours: pl.DataFrame,
    others: Sequence[pl.DataFrame],
    flagged: dict[str, Flag],
    model: InjuryModel | None,
    current_week: int,
    first_game_chance: dict[str, float] | None,
    stat_line: dict[tuple[str, int], float] | None,
    zero_is_missing: frozenset[str] = frozenset(),
) -> pl.DataFrame:
    """The source blend on the conditional scale. `ours` (gsis_id, week, projection) carries the
    chance of a stat line q when `stat_line` ((gsis_id, week) -> q, the `stat_line` table) is
    set: q comes out (E), E is blended with `others` (`blend_all`; an outside source is never
    divided by q), and q goes back on, except for games whose chance of playing will come from
    the injury table: that chance counts games with touches or targets, the stat-line event
    itself. The classifier's first-game chance (any offensive snaps) and healthy games keep q.
    A game with no q keeps ours as it is, with a warning."""
    if not stat_line:
        return blend_all(ours, others, "gsis_id", zero_is_missing)
    keys = list(zip(ours["gsis_id"], ours["week"], strict=True))
    missing = [f"{g} week {w}" for g, w in keys if (g, w) not in stat_line]
    if missing:
        warnings.warn(f"no stat-line chance for {missing}: q treated as 1", stacklevel=2)
    table = _table_games(ours, flagged, model, current_week, first_game_chance)
    q = [stat_line.get(k, 1.0) for k in keys]
    again = [1.0 if k in table else qk for k, qk in zip(keys, q, strict=True)]
    conditional = ours.with_columns(pl.col("projection") / pl.Series(q, dtype=pl.Float64))
    blended = blend_all(
        conditional.with_columns(pl.Series("_q", again, dtype=pl.Float64)),
        others,
        "gsis_id",
        zero_is_missing,
    )
    return blended.with_columns(pl.col("projection") * pl.col("_q")).drop("_q")


def injury_projections(
    projections: pl.DataFrame,
    flagged: dict[str, Flag],
    model: InjuryModel,
    current_week: int,
    first_game_chance: dict[str, float] | None = None,
) -> pl.DataFrame:
    """`projections` (gsis_id, week, projection) with each flagged player's rows multiplied by
    the chance he plays and the play-through ratio, plus a `play_prob` column.

    `first_game_chance` replaces the table's chance of playing the next game for the players it
    holds (a classifier scored better on the next game); later games keep the table's curve.

    `projection` becomes the expected points counting the chance of not playing; dividing by
    `play_prob` gives his points when he plays. A player's k-th game counts only his team's games,
    so a bye week does not use up a step of the curve."""
    curves = {g: _curve_or_questionable(model, f) for g, f in flagged.items()}
    override = first_game_chance or {}
    rows = _steps(projections, current_week)
    chance, factor = [], []
    for gsis, k in zip(rows["gsis_id"], rows["_k"], strict=True):
        curve = curves.get(gsis)
        if curve is None or k < 0:
            chance.append(1.0)
            factor.append(1.0)
            continue
        probs, perf = curve
        if k == 0 and gsis in override:
            chance.append(override[gsis])
        else:
            chance.append(probs[k] if k < len(probs) else 1.0)
        factor.append(1.0 + (perf - 1.0) * DECAY**k)
    p = pl.Series("play_prob", chance, dtype=pl.Float64)
    f = pl.Series("_factor", factor, dtype=pl.Float64)
    return (
        rows.with_columns(p, f)
        .with_columns(
            (pl.col("projection") * pl.col("_factor") * pl.col("play_prob")).alias("projection")
        )
        .drop("_k", "_factor")
    )
