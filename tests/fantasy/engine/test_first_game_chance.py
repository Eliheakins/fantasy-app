from pathlib import Path

import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim.league_projections import _first_game_chance

WEEK = 10


def write_week(data_dir: Path, report: dict[str, str | None]) -> None:
    """The classifier's chance (0.85) for every player, and this week's report: gsis id -> game
    status (None: on the report with practice rows only, as before Friday)."""
    season = load_config().season
    ids = list(report)
    store.write_table(
        "availability",
        pl.DataFrame(
            {"gsis_id": ids, "season": season, "week": WEEK, "p_play": [0.85] * len(ids)},
            schema_overrides={"season": pl.Int64, "week": pl.Int64},
        ),
        "derived",
        data_dir,
    )
    strings = "game_type team position full_name report_primary_injury practice_primary_injury"
    store.write_table(
        "nfl_injuries",
        pl.DataFrame(
            {
                "gsis_id": ids,
                "report_status": list(report.values()),
                "practice_status": ["Did Not Participate In Practice"] * len(ids),
                "season": season,
                "week": WEEK,
                **{c: ["x"] * len(ids) for c in strings.split()},
            },
            schema_overrides={
                "season": pl.Int64,
                "week": pl.Int64,
                "report_status": pl.String,
            },
        ).select(list(store.SCHEMAS["nfl_injuries"])),
        "raw",
        data_dir,
    )


def test_before_the_final_report_every_flagged_player_keeps_the_injury_table(
    tmp_path: Path,
) -> None:
    write_week(tmp_path, {"out": None, "doubtful": None, "questionable": None})
    flags = {
        "out": ("Out", "Knee", None),
        "doubtful": ("Doubtful", "Knee", None),
        "questionable": ("Questionable", "Hamstring", None),
    }
    assert _first_game_chance(WEEK, flags, tmp_path) == {}


def test_after_the_final_report_only_questionable_players_take_the_classifier(
    tmp_path: Path,
) -> None:
    write_week(tmp_path, {"out": "Out", "q": "Questionable", "downgraded": "Questionable"})
    flags = {
        "out": ("Out", "Knee", "DNP"),
        "q": ("Questionable", "Ankle", "Limited"),
        "downgraded": ("Out", "Ankle", "Limited"),  # Sleeper ruled him out after the report
    }
    assert _first_game_chance(WEEK, flags, tmp_path) == {"q": 0.85}
