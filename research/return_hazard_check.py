"""Do regulars who just returned from a missed game miss the next one more often than others?

The season simulation's absence chain has "out stays out" (STAY_OUT) and a flat chance of a
new absence (HAZARD) but no raised hazard for a player in his first game back. Universe: QB, RB,
WR and TE who averaged 50% or more of offensive snaps in their earlier games of the season (at
least 3), weeks 2 to 17 of 2019 onward. A missed game is any week with no offensive snaps, byes
included in both groups. State at week w: played w; compare those who also played w-1 against
those who missed w-1, on missing w+1.

    uv run python research/return_hazard_check.py
"""

import numpy as np
import polars as pl

from fantasy import store

MIN_PRIOR_GAMES = 3
REGULAR_SHARE = 0.5


def main() -> None:
    snaps = (
        store.read_table("nfl_snaps", "raw")
        .filter(
            pl.col("gsis_id").is_not_null()
            & pl.col("position").is_in(["QB", "RB", "WR", "TE"])
            & (pl.col("season") >= 2019)
        )
        .unique(["gsis_id", "season", "week"])
    )
    rows = []
    for (_, _), g in snaps.group_by("gsis_id", "season"):
        played = dict(zip(g["week"], g["offense_snaps"] > 0, strict=True))
        share = dict(zip(g["week"], g["offense_pct"], strict=True))
        for week in range(2, 18):
            prior = [share[w] for w in range(1, week) if w in share]
            if len(prior) < MIN_PRIOR_GAMES or np.mean(prior) < REGULAR_SHARE:
                continue
            if played.get(week, False):
                rows.append((played.get(week - 1, False), not played.get(week + 1, False)))
    frame = pl.DataFrame(rows, schema=["prev", "miss_next"], orient="row")
    for label, prev in (("played two straight", True), ("just returned after a miss", False)):
        group = frame.filter(pl.col("prev") == prev)
        p = float(group["miss_next"].mean())  # type: ignore[arg-type]
        se = (p * (1 - p) / group.height) ** 0.5
        print(f"{label:28s} n={group.height:5d}  miss next game {p:.3f} (se {se:.3f})")


if __name__ == "__main__":
    main()
