import json

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
