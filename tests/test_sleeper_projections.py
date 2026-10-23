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
