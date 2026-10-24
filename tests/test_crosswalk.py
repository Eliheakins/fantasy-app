import polars as pl

from fantasy import store
from fantasy.stages import crosswalk as c

PLAYER_COLS = ["sleeper_id", "full_name", "position", "team", "gsis_id"]
FF_SCHEMA = {
    "gsis_id": pl.String,
    "sleeper_id": pl.Int64,
    "name": pl.String,
    "merge_name": pl.String,
    "position": pl.String,
    "team": pl.String,
}
OVERRIDE_SCHEMA = {"sleeper_id": pl.String, "gsis_id": pl.String, "note": pl.String}
NO_OVERRIDES = pl.DataFrame(schema=OVERRIDE_SCHEMA)


def players(rows: list[tuple[str, str, str, str | None, str | None]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=dict.fromkeys(PLAYER_COLS, pl.String), orient="row")


def ff(rows: list[tuple[str | None, int | None, str, str, str, str]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=FF_SCHEMA, orient="row")


def method_by_id(df: pl.DataFrame) -> dict[str, str]:
    return dict(df.select("sleeper_id", "match_method").iter_rows())


def test_normalize_name_drops_suffixes_and_punctuation() -> None:
    assert c.normalize_name("Marvin Harrison Jr.") == "marvin harrison"
    assert c.normalize_name("Amon-Ra St. Brown") == "amonra st brown"


def test_team_codes_are_normalized() -> None:
    assert c.norm_team("LAR") == "LA" and c.norm_team("GBP") == "GB"
    assert c.norm_team("KC") == "KC" and c.norm_team(None) is None


def test_match_order_override_then_ffids_then_sleeper_file() -> None:
    pl_ = players(
        [
            ("1", "A One", "QB", "KC", "SLEEPERFILE1"),
            ("2", "B Two", "WR", "LAR", "SLEEPERFILE2"),
            ("3", "C Three", "RB", "BUF", "SLEEPERFILE3"),
            ("4", "D Four", "TE", None, None),
        ]
    )
    ffids = ff(
        [("FF1", 1, "A One", "a one", "QB", "KC"), ("FF2", 2, "B Two", "b two", "WR", "LAR")]
    )
    over = pl.DataFrame({"sleeper_id": ["2"], "gsis_id": ["OVR2"], "note": ["fix"]})
    df = c.build_id_map(pl_, ffids, over)
    store.check_schema("id_map", df)
    assert method_by_id(df) == {
        "1": "ffplayerids",
        "2": "override",
        "3": "sleeper_file",
        "4": "none",
    }
    assert df.filter(pl.col("sleeper_id") == "2")["gsis_id"].item() == "OVR2"


def test_name_position_team_fallback_requires_a_unique_match() -> None:
    pl_ = players(
        [("10", "Pat Rookie Jr.", "WR", "LAR", None), ("11", "Sam Twin", "RB", "CHI", None)]
    )
    ffids = ff(
        [
            ("G10", None, "Pat Rookie", "pat rookie", "WR", "LA"),
            ("G11a", None, "Sam Twin", "sam twin", "RB", "CHI"),
            ("G11b", None, "Sam Twin", "sam twin", "RB", "CHI"),
        ]
    )
    df = c.build_id_map(pl_, ffids, NO_OVERRIDES)
    assert method_by_id(df) == {"10": "name_pos_team", "11": "none"}


def test_defense_maps_by_team_code() -> None:
    rams = players([("LAR", "Los Angeles Rams", "DEF", "LAR", None)])
    df = c.build_id_map(rams, ff([]), NO_OVERRIDES)
    row = df.to_dicts()[0]
    assert row["match_method"] == "team_defense" and row["nfl_team"] == "LA"
    assert row["gsis_id"] is None


def test_only_my_unmapped_non_defense_players_are_flagged() -> None:
    id_map = pl.DataFrame(
        {
            "sleeper_id": ["1", "2", "3", "LAR"],
            "gsis_id": ["G1", None, None, None],
            "nfl_team": ["KC", None, None, "LA"],
            "match_method": ["ffplayerids", "none", "none", "team_defense"],
        }
    )
    rosters = pl.DataFrame(
        {
            "league_id": ["L"] * 5,
            "roster_id": [1, 1, 1, 1, 2],
            "sleeper_id": ["1", "2", "LAR", "99", "3"],
            "is_starter": [True] * 5,
            "is_ir": [False] * 5,
        }
    )
    teams = pl.DataFrame({"league_id": ["L", "L"], "roster_id": [1, 2], "is_me": [True, False]})
    pl_ = players(
        [
            ("1", "A", "QB", "KC", None),
            ("2", "B", "WR", None, None),
            ("3", "C", "RB", None, None),
            ("LAR", "Rams", "DEF", "LAR", None),
        ]
    )
    bad = c.unmapped_on_my_rosters(id_map, rosters, teams, pl_)
    assert sorted(bad["sleeper_id"].to_list()) == ["2", "99"]


def test_duplicate_gsis_lists_sleeper_ids_sharing_one_nflverse_id() -> None:
    id_map = pl.DataFrame(
        {"sleeper_id": ["1", "2", "3", "4"], "gsis_id": ["G", "G", "H", None]},
        schema={"sleeper_id": pl.String, "gsis_id": pl.String},
    )
    assert c.duplicate_gsis(id_map).to_dicts() == [{"gsis_id": "G", "sleeper_ids": ["1", "2"]}]


def test_rival_report_ignores_the_players_file_gsis_id_and_uses_the_map(capsys) -> None:
    id_map = pl.DataFrame(
        {
            "sleeper_id": ["1", "3"],
            "gsis_id": ["G1", None],
            "nfl_team": ["KC", None],
            "match_method": ["ffplayerids", "none"],
        }
    )
    rosters = pl.DataFrame({"league_id": ["L", "L"], "roster_id": [2, 2], "sleeper_id": ["1", "3"]})
    teams = pl.DataFrame({"league_id": ["L", "L"], "roster_id": [1, 2], "is_me": [True, False]})
    # the Sleeper players file carries its own gsis_id, empty for player 1
    pl_ = players([("1", "A", "QB", "KC", None), ("3", "C", "RB", None, None)]).with_columns(
        status=pl.lit("Active")
    )
    c.report_unmapped(id_map, rosters, teams, pl_)
    out = capsys.readouterr().out
    assert "unmapped on rival rosters: 1, e.g. C (RB)" in out
