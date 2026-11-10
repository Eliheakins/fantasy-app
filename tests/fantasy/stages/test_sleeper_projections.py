import json

import polars as pl

from fantasy.stages.sleeper_projections import snapshot_frame


def test_snapshot_keeps_players_with_stats_and_stores_them_as_json() -> None:
    items = [
        {"player_id": 4046, "stats": {"rec": 5.5, "rec_yd": 61.0}},
        {"player_id": "CHI", "stats": {"sack": 2.1}},
        {"player_id": "9999", "stats": {}},
        {"player_id": "8888"},
    ]
    frame = snapshot_frame(7, "2026-10-23T18:00:00+00:00", items)
    assert frame["sleeper_id"].to_list() == ["4046", "CHI"]
    assert frame["week"].to_list() == [7, 7]
    assert json.loads(frame["stats"][0]) == {"rec": 5.5, "rec_yd": 61.0}


def test_score_stats_maps_sleepers_coarse_kicker_buckets_to_league_scoring() -> None:
    from fantasy.stages.sleeper_projections import score_stats

    stats = {"fgm_30_39": 1.0, "fgm_50p": 0.5, "fgmiss_40_49": 0.2, "xpm": 2.0}
    league = {"fgm_30_39": 3.0, "fgm_50_59": 4.0, "fgmiss": -2.0, "xpm": 1.0}
    assert score_stats(stats, league) == 3.0 + 2.0 - 0.4 + 2.0
    specific = {"fgmiss_40_49": -3.0, "fgmiss": -1.0}
    assert score_stats({"fgmiss_40_49": 1.0, "fgmiss_30_39": 1.0}, specific) == -3.0 - 1.0


def test_blend_averages_where_sleeper_has_a_projection_and_keeps_ours_elsewhere() -> None:
    import polars as pl

    from fantasy.sim.blend import blend

    ours = pl.DataFrame({"gsis_id": ["a", "b"], "week": [7, 7], "projection": [10.0, 8.0]})
    theirs = pl.DataFrame({"gsis_id": ["a"], "week": [7], "other": [14.0]})
    out = blend(ours, theirs, "gsis_id")
    assert out["projection"].to_list() == [12.0, 8.0]


def test_blend_does_not_duplicate_rows_when_sleeper_has_two_rows_for_one_player_week() -> None:
    import polars as pl

    from fantasy.sim.blend import blend

    ours = pl.DataFrame({"gsis_id": ["a"], "week": [7], "projection": [10.0]})
    theirs = pl.DataFrame({"gsis_id": ["a", "a"], "week": [7, 7], "other": [14.0, 20.0]})
    assert blend(ours, theirs, "gsis_id").height == 1


def test_blend_ignores_a_sleeper_zero_only_for_keys_marked_zero_is_missing() -> None:
    import polars as pl

    from fantasy.sim.blend import blend

    ours = pl.DataFrame({"gsis_id": ["a", "b"], "week": [8, 8], "projection": [10.0, 10.0]})
    theirs = pl.DataFrame({"gsis_id": ["a", "b"], "week": [8, 8], "other": [0.0, 0.0]})
    out = blend(ours, theirs, "gsis_id", frozenset({"a"}))
    assert out.sort("gsis_id")["projection"].to_list() == [10.0, 5.0]


def snaps(*stat_lines: dict[str, float]) -> pl.DataFrame:
    items = [{"player_id": str(i), "stats": s} for i, s in enumerate(stat_lines)]
    return snapshot_frame(7, "2026-10-23T18:00:00+00:00", items)


def test_a_scored_stat_sleeper_no_longer_sends_is_named_and_flagged() -> None:
    from fantasy import _runs
    from fantasy.stages.sleeper_projections import scored_latest

    scoring = {"rec": 1.0, "rec_yd": 0.1, "bonus_rec_te": 0.5, "pass_td": 0.0}
    _runs._soft_failures.clear()
    scored_latest(snaps({"rec": 5.0, "rec_yd": 50.0}), scoring)
    assert len(_runs._soft_failures) == 1
    assert "bonus_rec_te" in _runs._soft_failures[0]
    assert "pass_td" not in _runs._soft_failures[0]  # zero weight: nothing lost
    _runs._soft_failures.clear()


def test_keys_sleeper_never_projects_for_offense_stay_quiet() -> None:
    from fantasy import _runs
    from fantasy.stages.sleeper_projections import scored_latest

    scoring = {"rec": 1.0, "pts_allow_0": 10.0, "sack": 1.0, "fgm_50_59": 5.0, "fgmiss": -1.0}
    _runs._soft_failures.clear()
    scored_latest(snaps({"rec": 5.0}), scoring)  # defense and kicker keys are bucketed elsewhere
    assert _runs._soft_failures == []
