"""Do the shipped environment effects replicate on seasons the fit did not see?

Fits `environment.estimate` on 2019 to 2023 and on 2024 onward separately and puts them next to
the all-seasons fit that production uses. An effect that cleared |t| of 2 on all seasons but has
the wrong sign or a t near zero in the later seasons is a winner's-curse candidate.

Run from the repo root: uv run python research/replication.py
"""

import polars as pl

from fantasy import store
from fantasy.sim.scoring_scale import reference_league
from fantasy.stages import environment

leagues = store.read_table("leagues", "raw")
league_id = reference_league(leagues)
season = int(leagues["season"].to_numpy().max())
panel = environment.history_panel(league_id, season)
parts = {
    "all": panel,
    "early": panel.filter(pl.col("season") < environment.SPLIT_SEASON),
    "late": panel.filter(pl.col("season") >= environment.SPLIT_SEASON),
}
tables = [
    environment.estimate(p)
    .select("position", "kind", "value", "t", "n")
    .with_columns(sample=pl.lit(s))
    for s, p in parts.items()
]
wide = (
    pl.concat(tables)
    .pivot(on="sample", index=["position", "kind"], values=["value", "t"])
    .sort("kind", "position")
)
with pl.Config(tbl_rows=60, tbl_cols=12):
    print(wide.with_columns(pl.col(pl.Float64).round(2)))
