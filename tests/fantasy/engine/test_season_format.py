"""Which leagues the season simulation can model: a 4, 6 or 8-team playoff ending by week 17.
Anything else (a guillotine league with no playoffs, a 5-team bracket) is left out
instead of crashing the refresh for everyone."""

import polars as pl
import pytest

from fantasy import _runs, store
from fantasy.sim.season import format_problem
from fantasy.stages import simulate as sim_stage


@pytest.mark.parametrize(
    ("teams", "playoff_teams", "start"),
    [(10, 6, 15), (12, 6, 14), (6, 6, 15), (14, 6, 15), (10, 4, 16), (12, 8, 15)],
)
def test_the_formats_the_app_models_pass(teams: int, playoff_teams: int, start: int) -> None:
    assert format_problem(teams, playoff_teams, start) is None


@pytest.mark.parametrize(
    ("teams", "playoff_teams", "start", "words"),
    [
        (16, None, 0, "no playoff"),  # a guillotine league: weekly eliminations, no bracket
        (16, 0, 0, "no playoff"),
        (10, 5, 15, "4, 6 or 8-team playoff"),
        (5, 6, 15, "at least 6 teams"),
        (10, 6, 0, "start week"),
        (10, 6, None, "start week"),
        (10, 6, 17, "start week"),  # a three-round bracket from week 17 would run past week 17
    ],
)
def test_the_formats_it_cannot_model_get_a_reason_in_plain_words(
    teams: int | None, playoff_teams: int | None, start: int | None, words: str
) -> None:
    problem = format_problem(teams, playoff_teams, start)
    assert problem is not None
    assert words in problem


def test_the_simulation_leaves_out_an_unmodelled_league_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leagues = pl.DataFrame(
        {
            "league_id": ["L9"],
            "league_key": ["sl-L9"],
            "num_teams": [16],
            "playoff_teams": [None],
            "playoff_week_start": [0],
        },
        schema={
            "league_id": pl.String,
            "league_key": pl.String,
            "num_teams": pl.Int64,
            "playoff_teams": pl.Int64,
            "playoff_week_start": pl.Int64,
        },
    )
    written: dict[str, pl.DataFrame] = {}

    def never_loaded(*args: object, **kwargs: object) -> None:
        raise AssertionError("an unmodelled league must not be loaded")

    monkeypatch.setattr(store, "read_table", lambda *a, **k: leagues)
    monkeypatch.setattr(sim_stage, "load_league_data", never_loaded)
    monkeypatch.setattr(store, "write_tables", lambda tables, **k: written.update(tables))
    _runs._soft_failures.clear()

    latest = sim_stage.run(archive=False)

    assert latest.is_empty()
    assert all(table.is_empty() for table in written.values())
    assert any("sl-L9" in note and "playoff" in note for note in _runs._soft_failures)
    _runs._soft_failures.clear()
