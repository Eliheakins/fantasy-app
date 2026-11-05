import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from scipy.special import gammaincc
from store_fixture import write_rows

from fantasy import store
from fantasy.stages import prop_points as pp

KICK = "2026-10-25T17:00:00Z"
SCHEDULE = pl.DataFrame(
    {
        "season": [2026],
        "week": [7],
        "gameday": ["2026-10-25"],
        "gametime": ["13:00"],
        "away_team": ["PIT"],
        "home_team": ["BAL"],
    }
)


def market(key: str, player: str, point: float, over: float, under: float) -> dict:
    return {
        "key": key,
        "outcomes": [
            {"name": "Over", "description": player, "price": over, "point": point},
            {"name": "Under", "description": player, "price": under, "point": point},
        ],
    }


def event(markets: list[dict], books: tuple[str, ...] = ("fanduel",)) -> dict:
    return {
        "id": "e1",
        "commence_time": KICK,
        "home_team": "Baltimore Ravens",
        "away_team": "Pittsburgh Steelers",
        "bookmakers": [{"key": b, "markets": markets} for b in books],
    }


def write_snapshot(odds_dir: Path, stamp: str, ev: dict) -> None:
    folder = odds_dir / stamp
    folder.mkdir(parents=True)
    (folder / "e1.json").write_text(json.dumps(ev))


def test_a_coin_flip_yardage_line_is_scaled_by_r_and_extreme_prices_are_clamped() -> None:
    r, sigma = pp.PROP_FIT["player_rush_yds"]
    assert pp.prop_mean("player_rush_yds", 60.5, 0.5) == pytest.approx(r * 60.5)
    assert pp.prop_mean("player_rush_yds", 60.5, 0.999) == pytest.approx(r * (60.5 + sigma))
    assert pp.prop_mean("player_rush_yds", 60.5, 0.001) == pytest.approx(r * (60.5 - sigma))


def test_receptions_mean_inverts_the_poisson_over_probability() -> None:
    r, _ = pp.PROP_FIT["player_receptions"]
    p_over = 1 - gammaincc(4, 4.2)  # P(X > 3.5) for lambda 4.2
    assert pp.prop_mean("player_receptions", 3.5, p_over) == pytest.approx(r * 4.2)
    # an integer line: Over means X >= 5, so P(X > 4) = 1 - P(X <= 4) = 1 - Q(5, lambda)
    p_over = 1 - gammaincc(5, 4.2)
    assert pp.prop_mean("player_receptions", 4.0, p_over) == pytest.approx(r * 4.2)


def test_event_lines_devigs_paired_prices_and_skips_one_sided_lines() -> None:
    lone = {
        "key": "player_rush_yds",
        "outcomes": [{"name": "Over", "description": "X", "price": -110, "point": 9.5}],
    }
    ev = event([market("player_rush_yds", "Derrick Henry", 80.5, -120, 100), lone])
    rows = pp.event_lines(ev, datetime(2026, 10, 24, tzinfo=UTC))
    assert len(rows) == 1
    q_over, q_under = 120 / 220, 100 / 200
    assert rows[0]["p_over"] == pytest.approx(q_over / (q_over + q_under))
    assert (rows[0]["home"], rows[0]["away"], rows[0]["line"]) == ("BAL", "PIT", 80.5)


def test_week_lines_keep_the_latest_snapshot_before_kickoff_and_average_books(
    tmp_path: Path,
) -> None:
    write_snapshot(
        tmp_path, "20261023T120000Z", event([market("player_rush_yds", "A B", 50.5, -110, -110)])
    )
    two_books = event([market("player_rush_yds", "A B", 70.5, -110, -110)], ("fanduel", "dk"))
    write_snapshot(tmp_path, "20261025T163000Z", two_books)
    late = event([market("player_rush_yds", "A B", 99.5, -110, -110)])
    write_snapshot(tmp_path, "20261025T171500Z", late)  # after kickoff: ignored
    out = pp.week_lines(pp.read_snapshots(tmp_path), SCHEDULE)
    r, _ = pp.PROP_FIT["player_rush_yds"]
    assert out.height == 1
    assert out["prop_mean"].item() == pytest.approx(r * 70.5)


def test_a_snapshot_taken_too_long_before_its_games_kickoff_is_stale(tmp_path: Path) -> None:
    line = event([market("player_rush_yds", "A B", 50.5, -110, -110)])
    write_snapshot(tmp_path, "20261024T040000Z", line)  # 37 hours before the 17:00Z kickoff
    assert pp.week_lines(pp.read_snapshots(tmp_path), SCHEDULE).is_empty()
    write_snapshot(tmp_path, "20261024T060000Z", line)  # 35 hours: a Sunday pull for Monday night
    assert pp.week_lines(pp.read_snapshots(tmp_path), SCHEDULE).height == 1
    assert pp.read_snapshots(tmp_path / "missing").is_empty()


def test_a_game_without_a_kickoff_time_and_a_truncated_odds_file_do_not_raise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_snapshot(
        tmp_path, "20261025T163000Z", event([market("player_rush_yds", "A B", 70.5, -110, -110)])
    )
    (tmp_path / "20261025T163000Z" / "e2.json").write_text('{"id": "e2", "bookm')
    (tmp_path / "20261025T163000Z" / "e3.json").write_text('{"id": "e3"}')
    lines = pp.read_snapshots(tmp_path)
    assert lines.height == 1
    assert capsys.readouterr().out.count("warning: odds file") == 2
    no_time = pl.concat([SCHEDULE, SCHEDULE.with_columns(gametime=pl.lit(None, pl.String))])
    assert pp.week_lines(lines, no_time).height == 1  # the odds file has the kickoff
    no_day = SCHEDULE.with_columns(
        gameday=pl.lit(None, pl.String), gametime=pl.lit(None, pl.String)
    )
    assert pp.week_lines(lines, no_day).is_empty()


def test_map_players_matches_a_unique_name_within_the_games_two_teams() -> None:
    lines = pl.DataFrame(
        {
            "home": ["BAL", "BAL"],
            "away": ["PIT", "PIT"],
            "player": ["Derrick Henry Jr.", "Same Name"],
            "market": ["player_rush_yds"] * 2,
            "prop_mean": [80.0, 10.0],
        }
    )
    people = pl.DataFrame(
        {
            "gsis_id": ["g1", "g2", "g3", "g4"],
            "name": ["Derrick Henry", "Same Name", "Same Name", "Derrick Henry"],
            "position": ["RB", "WR", "WR", "RB"],
            "team": ["BAL", "BAL", "PIT", "TEN"],
        }
    )
    out = pp.map_players(lines, people)
    assert out.select("gsis_id", "position").rows() == [("g1", "RB")]


def stat_rows(weeks: list[int], **stats: float) -> list[dict]:
    blank = dict.fromkeys(store.SCHEMAS["nfl_player_stats"])
    return [{**blank, "player_id": "g1", "season": 2026, "week": w, **stats} for w in weeks]


def test_lagged_means_use_only_the_last_games_before_the_week() -> None:
    weeks = list(range(1, 12))
    points = pl.DataFrame(
        {"gsis_id": "g1", "season": 2026, "week": weeks, "points": [20.0] * 10 + [99.0]}
    )
    stats = pl.DataFrame(
        stat_rows(weeks[:10], rushing_yards=50.0, receptions=2.0, rushing_fumbles_lost=0.5)
        + stat_rows([11], rushing_yards=500.0),
        schema=store.SCHEMAS["nfl_player_stats"],
    )
    scoring = {"rush_yd": 0.1, "rec": 1.0, "fum_lost": -2.0}
    lags = pp.lagged_means(points, stats, scoring, 2026, 11)
    row = lags.row(0, named=True)
    assert row["n_games"] == pp.LAG_GAMES
    assert row["rushing_yards"] == pytest.approx(50.0)
    # rest: 20 - (50 * 0.1 + 2 * 1) = 13; unprojected: 0.5 fumbles lost * -2
    assert row["rest"] == pytest.approx(13.0)
    assert row["unprojected"] == pytest.approx(-1.0)


def test_implied_points_add_lagged_rest_and_fill_unlined_stats_from_lags() -> None:
    props = pl.DataFrame(
        {
            "gsis_id": ["rb", "wr", "wr2", "qb", "new"],
            "position": ["RB", "WR", "WR", "QB", "RB"],
            "market": [
                "player_rush_yds",
                "player_receptions",
                "player_receptions",
                "player_pass_yds",
                "player_rush_yds",
            ],
            "prop_mean": [80.0, 5.0, 4.0, 250.0, 60.0],
        }
    )
    props = pl.concat(
        [
            props,
            pl.DataFrame(
                {
                    "gsis_id": ["wr"],
                    "position": ["WR"],
                    "market": ["player_reception_yds"],
                    "prop_mean": [60.0],
                }
            ),
        ]
    )
    lags = pl.DataFrame(
        {
            "gsis_id": ["rb", "wr", "wr2", "qb"],
            "n_games": [8] * 4,
            "passing_yards": [0.0] * 4,
            "rushing_yards": [70.0, 5.0, 0.0, 10.0],
            "receptions": [3.0, 4.0, 4.0, 0.0],
            "receiving_yards": [20.0, 50.0, 50.0, 0.0],
            "rest": [6.0, 4.0, 4.0, 8.0],
            "unprojected": [0.0] * 4,
        }
    )
    scoring = {"rush_yd": 0.1, "rec": 1.0, "rec_yd": 0.1, "pass_yd": 0.04}
    out = pp.implied_points(props, lags, scoring, ("RB", "WR"))
    got = dict(out.select("gsis_id", "projection").iter_rows())
    # rb: 80 * 0.1 + lagged 3 receptions and 20 yards (3 + 2) + rest 6; wr: 0.5 + 5 + 6 + 4.
    # wr2 has no receiving-yards line, qb is not a blended position, new has no earlier game
    assert got == pytest.approx({"rb": 8.0 + 5.0 + 6.0, "wr": 0.5 + 5.0 + 6.0 + 4.0})


def test_outside_points_score_under_the_league_add_fumbles_and_remove_the_bias() -> None:
    snaps = pl.DataFrame(
        {
            "source": ["fftoday"] * 3,
            "fetched_at": ["t1", "t2", "t1"],
            "position": ["WR", "WR", "RB"],
            "gsis_id": ["g1", "g1", "g2"],
            "stats": [
                json.dumps({"rec": 9.0}),
                json.dumps({"rec": 5.0, "rec_yd": 60.0}),
                json.dumps({"rec": 2.0}),
            ],
        }
    )
    lags = pl.DataFrame({"gsis_id": ["g1"], "unprojected": [-0.2]})
    out = pp.outside_points(snaps, {"rec": 0.5, "rec_yd": 0.1}, lags, bias={"WR": 1.5})
    got = {r["gsis_id"]: r for r in out.iter_rows(named=True)}
    # the latest fetch per position: WR from t2, RB keeps its only (earlier) fetch
    assert (got["g1"]["fetched_at"], got["g2"]["fetched_at"]) == ("t2", "t1")
    assert got["g1"]["projection"] == pytest.approx(2.5 + 6.0 - 0.2 - 1.5)
    assert got["g2"]["projection"] == pytest.approx(1.0)


def outside_store(tmp_path: Path) -> None:
    write_rows(
        tmp_path, "leagues", [{"league_id": "L1", "current_week": 7, "scoring_settings": "{}"}]
    )
    write_rows(tmp_path, "nfl_schedules", SCHEDULE.to_dicts())
    write_rows(tmp_path, "player_points")
    write_rows(tmp_path, "nfl_injuries")
    players = (("1", "Wide Out", "WR"), ("2", "Run Back", "RB"))
    write_rows(
        tmp_path,
        "sleeper_players",
        [{"sleeper_id": s, "full_name": n, "position": p, "team": "BAL"} for s, n, p in players],
    )
    write_rows(tmp_path, "id_map", [{"sleeper_id": s, "gsis_id": f"g{s}"} for s in ("1", "2")])
    stats = pl.DataFrame(schema=store.SCHEMAS["nfl_player_stats"])
    store.write_table("nfl_player_stats", stats, "raw", tmp_path)


def test_run_drops_outside_rows_fetched_before_the_weeks_window_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_store(tmp_path)
    base = {"source": "fftoday", "season": 2026, "week": 7, "team": "BAL", "stats": "{}"}
    snaps = [
        {**base, "fetched_at": "2026-10-19T12:00:00+00:00", "position": "RB", "name": "Run Back"},
        {**base, "fetched_at": "2026-10-23T12:00:00+00:00", "position": "WR", "name": "Wide Out"},
    ]
    store.write_table(
        "outside_proj_snapshots",
        pl.DataFrame(snaps, schema=store.SCHEMAS["outside_proj_snapshots"]),
        "archive",
        tmp_path,
    )
    assert pp.run(tmp_path, tmp_path / "odds") == (0, 1)
    out = capsys.readouterr().out
    assert "fftoday WR fetched" in out and "hours" in out
    assert "warning: fftoday has no rows for ['QB', 'RB', 'TE']" in out


def test_a_failure_in_the_props_half_leaves_props_empty_and_keeps_outside_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_store(tmp_path)

    def broken(*args: object) -> pl.DataFrame:
        raise RuntimeError("bad snapshot")

    monkeypatch.setattr(pp, "map_players", broken)
    assert pp.run(tmp_path, tmp_path / "odds") == (0, 0)
    assert "warning: prop points skipped" in capsys.readouterr().out
    assert store.read_table("proj_props", "derived", tmp_path).is_empty()


def test_run_without_odds_or_outside_snapshots_writes_empty_tables(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_rows(
        tmp_path, "leagues", [{"league_id": "L1", "current_week": 7, "scoring_settings": "{}"}]
    )
    write_rows(tmp_path, "nfl_schedules", SCHEDULE.to_dicts())
    for name in ("sleeper_players", "id_map", "player_points", "nfl_injuries"):
        write_rows(tmp_path, name)
    stats = pl.DataFrame(schema=store.SCHEMAS["nfl_player_stats"])
    store.write_table("nfl_player_stats", stats, "raw", tmp_path)
    assert pp.run(tmp_path, tmp_path / "archive" / "odds") == (0, 0)
    assert store.read_table("proj_props", "derived", tmp_path).is_empty()
    assert store.read_table("proj_outside", "derived", tmp_path).is_empty()
    assert "no odds snapshot" in capsys.readouterr().out
