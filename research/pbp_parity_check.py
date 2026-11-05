"""Parity check for the shared play-by-play cache (issue #70, S4a).

Computes `nfl_team_pace` (ingest_role.load_pace) and the team-efficiency table
(environment.team_efficiency) twice, in memory, on the same day: the old way (nflreadpy
`load_pbp`, its own download) and the new way (through `nfl_stat.pipeline.pbp_source`, which
downloads into data/raw/pbp/). Sorts both and compares with DataFrame.equals, per season and per
column, dtypes included. Writes only data/raw/pbp/; no table under data/raw, derived or archive.

Run: uv run python research/pbp_parity_check.py   (needs the network, takes minutes)
"""

import sys
from collections.abc import Callable

import nflreadpy
import polars as pl

from fantasy.config import load_config
from fantasy.stages import environment, ingest_role

FIRST = 2018


def old_read(season: int, columns: list[str] | None = None) -> pl.DataFrame:
    return nflreadpy.load_pbp([season])  # all columns, as before; `columns` is ignored on purpose


def run_both(
    module: object, compute: Callable[[], pl.DataFrame]
) -> tuple[pl.DataFrame, pl.DataFrame]:
    new_read = module.read_pbp  # type: ignore[attr-defined]
    module.read_pbp = old_read  # type: ignore[attr-defined]
    try:
        old = compute()
    finally:
        module.read_pbp = new_read  # type: ignore[attr-defined]
    return old, compute()


def compare(name: str, old: pl.DataFrame, new: pl.DataFrame, keys: list[str]) -> bool:
    ok = True
    print(f"\n== {name}: old {old.shape}, new {new.shape}")
    if old.columns != new.columns:
        print(f"  COLUMNS DIFFER: {old.columns} vs {new.columns}")
        return False
    old, new = old.sort(keys), new.sort(keys)
    print(f"  dtypes old {dict(old.schema)}")
    for col in old.columns:
        if old.schema[col] != new.schema[col]:
            print(f"  DTYPE DIFFERS {col}: {old.schema[col]} vs {new.schema[col]}")
            ok = False
    for season in sorted(old["season"].unique().to_list()):
        o, n = old.filter(pl.col("season") == season), new.filter(pl.col("season") == season)
        cols = {c: o[c].equals(n[c]) for c in old.columns} if o.height == n.height else {}
        same = o.height == n.height and o.equals(n)
        bad = [c for c, v in cols.items() if not v]
        print(f"  {season}: rows {o.height}/{n.height} equal={same} differing columns={bad}")
        ok &= same
    whole = old.equals(new)
    print(f"  whole table equals: {whole}")
    return ok and whole


def main() -> int:
    last = load_config().season
    pace_old, pace_new = run_both(ingest_role, ingest_role.load_pace)
    eff_old, eff_new = run_both(
        environment, lambda: environment.team_efficiency(range(FIRST, last + 1))
    )
    results = [
        compare("nfl_team_pace", pace_old, pace_new, ["team", "season", "week"]),
        compare("team efficiency", eff_old, eff_new, ["season", "week", "team", "opponent"]),
    ]
    print("\nPARITY:", "EXACT" if all(results) else "DIFFERENT")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
