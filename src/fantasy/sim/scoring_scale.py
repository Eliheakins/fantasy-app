"""Carry point-valued effects from the league they were measured in to another league.

The outlook and environment effects are measured once, in points under the reference league's
scoring. A league that scores less per reception has smaller point effects, so they are scaled
by the league's mean projection per position relative to the reference league's. Ratio effects
(first game back and the like) need no scaling.
"""

import polars as pl

Effects = dict[tuple[str, str], float]  # (position, kind) -> value


def reference_league(leagues: pl.DataFrame) -> str:
    """The league the effects are measured in: the same one on every run."""
    return str(min(leagues["league_id"].to_list()))


def position_scale(baseline: pl.DataFrame, league_id: str, reference_id: str) -> dict[str, float]:
    """Mean projection per position in `league_id` over the reference league's.
    `baseline` has league_id, position and projection."""
    means = baseline.group_by("league_id", "position").agg(pl.col("projection").mean())
    by_league = {
        (r["league_id"], r["position"]): r["projection"] for r in means.iter_rows(named=True)
    }
    positions = {p for _, p in by_league}
    return {
        p: by_league[(league_id, p)] / by_league[(reference_id, p)]
        for p in positions
        if by_league.get((reference_id, p)) and (league_id, p) in by_league
    }


def scale_points(effects: Effects, scale: dict[str, float], kinds: frozenset[str]) -> Effects:
    """`effects` with each point-valued kind multiplied by its position's scale. A position with
    a point-valued effect but no scale would silently keep the reference league's points, so it
    raises."""
    unscaled = {pos for (pos, kind) in effects if kind in kinds and pos not in scale}
    if unscaled:
        raise ValueError(
            f"no scoring scale for {sorted(unscaled)}: a point-valued effect would be applied "
            "unscaled (position missing from the league or the reference league)"
        )
    return {
        (position, kind): value * scale[position] if kind in kinds else value
        for (position, kind), value in effects.items()
    }
