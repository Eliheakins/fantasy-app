"""Turn an injury report into a chance of playing each of the next games, and a play-through
discount, using the table `stages/injuries.py` measures.

A flagged player gets a curve: the chance he plays in each of his team's next four games, then
healthy. Hamstrings, feet and ankles come back slower than groins and shoulders, and a
Questionable player who did not practice plays far less often than one who practiced in full.
While he plays through it his projection is discounted by a ratio that halves each week.

Long-term designations (IR, PUP and so on) keep the four-game minimum. A status the table does
not cover leaves the player healthy.
"""

import polars as pl

from fantasy.sim.availability import LONG_TERM, LONG_TERM_WEEKS

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
    curves = {g: model.curve(f) for g, f in flagged.items()}
    override = first_game_chance or {}
    rows = projections.sort("gsis_id", "week").with_columns(
        pl.col("week").rank("ordinal").over("gsis_id").alias("_game")
    )
    ahead = rows.filter(pl.col("week") >= current_week)
    first = ahead.group_by("gsis_id").agg(pl.col("_game").min())
    start = dict(zip(first["gsis_id"], first["_game"], strict=True))
    chance, factor = [], []
    for gsis, week, game in zip(rows["gsis_id"], rows["week"], rows["_game"], strict=True):
        curve = curves.get(gsis)
        k = game - start.get(gsis, game) if week >= current_week else -1
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
        .drop("_game", "_factor")
    )
