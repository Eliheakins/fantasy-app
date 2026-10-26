"""Fit the prop-mean constants the prop_points stage uses (r_m and sigma_m per market).

Same method and archive as props_check.py (read its docstring for the download): yardage mean =
r_m * (L + z * sigma_m), z = Phi^-1(de-vigged p_over) clamped to +/-1; receptions mean = r_m *
Poisson lambda. Fit on every 2024 and 2025 line the free archive has: passing yards and
receptions from the FanDuel history files (2024-2025), rushing and receiving yards from the 2024
merged file (the only one with those markets). Copy the printed numbers into
src/fantasy/stages/prop_points.py (PROP_FIT).

Run from the repo root: uv run python research/prop_constants.py [archive dir]
"""

import sys
from pathlib import Path

import polars as pl

import props_check as pc
from fantasy import store

FIT_SEASONS = (2024, 2025)


def main() -> None:
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else pc.ARCHIVE
    schedule = store.read_table("nfl_schedules", "raw")
    stats = store.read_table("nfl_player_stats", "raw")
    abbr = pc.team_abbr(archive)
    files = (pc.TEST_FILE, *pc.FIT_FILES)
    lines = pl.concat([pc.load_lines(archive / f, abbr, schedule) for f in files], how="diagonal_relaxed")
    lines = lines.filter(pl.col("season").is_in(FIT_SEASONS))
    # the merged file repeats some history-file lines: keep one per game, player and market
    lines = lines.sort("snap").unique(["game_id", "name", "market_key"], keep="last")
    rows = pc.with_raw_mean(pc.match_players(lines, stats))
    for market in pc.MARKETS:
        g = rows.filter(pl.col("market_key") == market)
        r, sigma = pc.fit_market(g, market)
        print(f"{market:22} n {g.height:5} seasons {sorted(g['season'].unique().to_list())} r {r:.4f} sigma {sigma:.2f}")


if __name__ == "__main__":
    main()
