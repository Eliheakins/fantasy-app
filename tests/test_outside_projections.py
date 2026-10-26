import json
from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows

from fantasy import store
from fantasy.config import load_config
from fantasy.stages import outside_projections as op

# hand-written, synthetic rows in FFToday's page layout (not real projections)
HEAD = (
    "<TR><TD>Sort First: <A>x</A></TD><TD>Last: </TD><TD><B>Team</B></TD><TD><B>Opp</B></TD>{}"
    "<TD><B>FPts</B><BR><A HREF='?order_by=FFPts'><IMG></A></TD></TR>"
)
ROW = (
    '<TR>\n<TD class="bodycontent">&nbsp;</TD>\n<TD class="smallbody">&nbsp;'
    '<A HREF="/stats/players/{pid}/Some_Name?LeagueID=1">{name}</A>   </TD>\n'
    "{cells}</TR>"
)


def page(labels: str, rows: list[tuple[str, str, list[str]]]) -> str:
    head = HEAD.format("".join(f"<TD><B>{x}</B><BR></TD>" for x in labels.split()))
    body = "".join(
        ROW.format(pid=i + 100, name=name, cells="".join(f"<TD>{c}</TD>\n" for c in cells))
        for i, (name, _, cells) in enumerate(rows)
    )
    return f"<html><TABLE>{head}{body}</TABLE></html>"


RB_PAGE = page(
    "Att Yard TD Rec Yard TD",
    [
        ("Alpha Back", "", ["LAR", "@KC", "15.0", "70.0", "0.5", "3.0", "20.0", "0.1", "12.6"]),
        ("Beta Back Jr.", "", ["JAC", "TEN", "10.0", "1,040.0", "0.2", "1.0", "8.0", "0.0", "6.0"]),
    ],
)
QB_PAGE = page(
    "Comp Att Yard TD INT Att Yard TD",
    [
        (
            "Gamma Passer",
            "",
            ["BUF", "MIA", "21", "31", "241", "1.5", "0.3", "9", "44", "0.7", "26.7"],
        )
    ],
)


def test_parse_fftoday_maps_columns_to_sleeper_stat_keys() -> None:
    rows = op.parse_fftoday(RB_PAGE, "RB")
    assert [r["name"] for r in rows] == ["Alpha Back", "Beta Back Jr."]
    assert rows[0]["source_id"] == "100" and rows[0]["team"] == "LA"  # nflverse team codes
    assert rows[1]["team"] == "JAX"
    assert rows[0]["stats"] == {
        "rush_att": 15.0, "rush_yd": 70.0, "rush_td": 0.5, "rec": 3.0, "rec_yd": 20.0, "rec_td": 0.1
    }  # fmt: skip
    assert rows[1]["stats"]["rush_yd"] == 1040.0  # thousands separator dropped
    qb = op.parse_fftoday(QB_PAGE, "QB")[0]["stats"]
    assert qb["pass_cmp"] == 21.0 and qb["pass_int"] == 0.3 and qb["rush_yd"] == 44.0


def test_parse_fftoday_rejects_a_changed_layout() -> None:
    with pytest.raises(ValueError, match="layout"):
        op.parse_fftoday(RB_PAGE.replace("<B>Rec</B>", "<B>Tgt</B>"), "RB")
    with pytest.raises(ValueError, match="no player rows"):
        op.parse_fftoday(page("Att Yard TD Rec Yard TD", []), "RB")


def test_run_appends_to_the_archive_and_a_failing_position_does_not_stop_it(
    tmp_path: Path,
) -> None:
    write_rows(tmp_path, "leagues", [{"league_id": "L", "current_week": 7}])

    def fake(season: int, week: int, position: str) -> str:
        if position == "QB":
            raise RuntimeError("site down")
        return RB_PAGE

    sources = {"fftoday": fake}
    assert op.run(tmp_path, ["fftoday"], sources, pause=0) == 6  # RB, WR, TE pages, 2 rows each
    assert op.run(tmp_path, ["fftoday"], sources, pause=0) == 6
    archive = store.read_table("outside_proj_snapshots", "archive", tmp_path)
    assert archive.height == 12  # appended, not replaced
    assert set(archive["position"]) == {"RB", "WR", "TE"}
    assert archive["week"].unique().to_list() == [7]
    assert json.loads(archive["stats"][0])["rush_yd"] == 70.0


def test_run_writes_nothing_when_every_fetch_fails_or_no_source_is_on(tmp_path: Path) -> None:
    write_rows(tmp_path, "leagues", [{"league_id": "L", "current_week": 7}])

    def down(season: int, week: int, position: str) -> str:
        raise RuntimeError("site down")

    assert op.run(tmp_path, ["fftoday"], {"fftoday": down}, pause=0) == 0
    assert op.run(tmp_path, [], {"fftoday": down}, pause=0) == 0
    assert not store.table_path("outside_proj_snapshots", "archive", tmp_path).exists()


def test_map_to_gsis_matches_name_position_and_team_then_unique_name() -> None:
    snaps = pl.DataFrame(
        {
            "name": ["Alpha Back", "Beta Back Jr.", "Chris Same", "Chris Same", "Nobody"],
            "position": ["RB", "RB", "WR", "WR", "TE"],
            "team": ["LA", "JAX", "DAL", "NYG", "SF"],
        }
    )
    people = pl.DataFrame(
        {
            "gsis_id": ["a", "b", "c1", "c2"],
            "name": ["Alpha Back", "Beta Back", "Chris Same", "Chris Same"],
            "position": ["RB", "RB", "WR", "WR"],
            "team": ["KC", "JAX", "DAL", "NYG"],
        }
    )
    out = op.map_to_gsis(snaps, people)
    # Alpha changed teams: unique on name and position; Chris needs the team to tell them apart
    assert out["gsis_id"].to_list() == ["a", "b", "c1", "c2", None]


def test_config_reads_outside_sources_and_rejects_unknown_ones(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    body = 'season = 2026\nuser_id = "u"\nn_sims = 1\n{}\n[leagues.a]\nid = "1"\n'
    path.write_text(body.format('outside_sources = ["fftoday"]'))
    assert load_config(path).outside_sources == ("fftoday",)
    path.write_text(body.format(""))
    assert load_config(path).outside_sources == ()
    path.write_text(body.format('outside_sources = ["espn"]'))
    with pytest.raises(ValueError, match="outside_sources"):
        load_config(path)
