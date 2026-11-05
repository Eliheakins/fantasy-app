"""Helpers that build a tiny parquet store in a temporary directory."""

from pathlib import Path

import polars as pl

from fantasy import store

RAW = {
    "leagues",
    "league_teams",
    "rosters",
    "matchups",
    "matchup_players",
    "sleeper_players",
    "nfl_injuries",
    "nfl_schedules",
}


def write_rows(tmp_path: Path, name: str, rows: list[dict] | None = None) -> None:
    """Write a table from dict rows; columns a row leaves out are null, no rows is empty."""
    schema = store.SCHEMAS[name]
    blank = dict.fromkeys(schema)
    df = pl.DataFrame([{**blank, **r} for r in rows or []], schema=schema)
    store.write_table(name, df, "raw" if name in RAW else "derived", tmp_path)


LID = "L1"
POSITIONS = ["QB", "RB", "K", "BN", "BN"]
# weeks 1 and 2 scored; later weeks are the zero-point placeholders Sleeper pre-fills
SCORES = {1: {1: 100.0, 2: 90.0, 3: 80.0, 4: 70.0}, 2: {1: 60.0, 3: 95.0, 2: 75.0, 4: 75.0}}
PAIRS = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)], 3: [(1, 4), (2, 3)], 4: [(1, 2), (3, 4)]}

LEVELS = range(1, 100)
SKILL = (("G_QB", "QB"), ("G_WR", "WR"), ("G_RB", "RB"), ("G_OPP", "WR"))


def _engine_store(tmp_path: Path) -> None:
    from test_simulate_load import build_store  # lazy: that module imports this one

    build_store(tmp_path, [(100.0, 90.0)])
    write_rows(tmp_path, "trending")
    marginals = [
        {
            "league_id": "L1",
            "position": pos,
            "tier": tier,
            "tau": round(k / 100, 2),
            "ratio": 0.4 + k / 100 + 0.1 * tier,
            "cv": 0.5,
            "proj_max": {0: 8.0, 1: 14.0}.get(tier),
        }
        for pos in ("QB", "RB", "WR", "TE")
        for tier in (-1, 0, 1, 2)
        for k in LEVELS
    ]
    write_rows(tmp_path, "marginals", marginals)
    points = [
        {"league_id": "L1", "gsis_id": g, "season": 2026, "week": w, "points": 5.0 + w + len(g) % 3}
        | {"season_type": "REG", "position": pos}
        for g, pos in SKILL
        for w in (1, 2)
    ]
    write_rows(tmp_path, "player_points", points)
    schema = store.SCHEMAS["nfl_ff_opportunity"]
    opportunity = [
        {"player_id": g, "season": 2026, "week": w, "position": pos, "posteam": "KC"}
        | {"total_fantasy_points_exp": 7.0, "rec_attempt": 5.0, "receptions_exp": 4.0}
        for g, pos in SKILL
        for w in (1, 2)
    ]
    frame = pl.DataFrame([{**dict.fromkeys(schema), **r} for r in opportunity], schema=schema)
    store.write_table("nfl_ff_opportunity", frame, "raw", tmp_path)
