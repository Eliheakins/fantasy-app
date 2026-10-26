import polars as pl
import pytest

from fantasy.stages import vacancy

KEY = {"gsis_id": pl.String, "season": pl.Int64, "week": pl.Int64}
REPORT = {**KEY, "team": pl.String, "position": pl.String, "status": pl.String,
          "practice": pl.String}  # fmt: skip
WEIGHTS = {"Full": 0.25, "Limited": 0.35, "DNP": 0.6, None: 0.4}


def usage(rows: list[tuple[str, int, float, float, float]], team: str = "KC") -> pl.DataFrame:
    """(player, week, target share, carry share, snap share) for `team` in 2025."""
    return pl.DataFrame(
        [(g, 2025, w, team, t, c, s) for g, w, t, c, s in rows],
        schema={**KEY, "team": pl.String, "tgt": pl.Float64, "car": pl.Float64,
                "snap": pl.Float64},
        orient="row",
    )  # fmt: skip


def sleeper(statuses: list[str | None], ids: list[str]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Sleeper players (their own gsis_id column mostly null, as in the real file) and id_map."""
    sleeper_ids = [str(i) for i in range(len(statuses))]
    players = pl.DataFrame(
        {
            "sleeper_id": sleeper_ids,
            "gsis_id": [None] * len(statuses),
            "position": ["WR"] * len(statuses),
            "team": ["KC"] * len(statuses),
            "injury_status": statuses,
        },
        schema_overrides={"gsis_id": pl.String},
    )
    return players, pl.DataFrame({"sleeper_id": sleeper_ids, "gsis_id": ids})


def report(rows: list[tuple[str, int, str, str | None, str | None]]) -> pl.DataFrame:
    """(player, week, position, status, practice) for KC in 2025."""
    return pl.DataFrame(
        [(g, 2025, w, "KC", p, s, pr) for g, w, p, s, pr in rows], schema=REPORT, orient="row"
    )


def targets(player: str, week: int, depth: float | None = 2.0) -> pl.DataFrame:
    return pl.DataFrame(
        [(player, 2025, week, "KC", "WR", depth)],
        schema={**KEY, "team": pl.String, "position": pl.String, "depth_rank": pl.Float64},
        orient="row",
    )


def depth(rows: list[tuple[str, int, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [(g, 2025, w, r) for g, w, r in rows],
        schema={**KEY, "depth_rank": pl.Float64},
        orient="row",
    )


def features(rep: pl.DataFrame, use: pl.DataFrame, chart: pl.DataFrame | None = None) -> dict:  # type: ignore[type-arg]
    chart = depth([]) if chart is None else chart
    return vacancy.vacancy_features(targets("A", 3), rep, use, WEIGHTS, chart).row(0, named=True)


def test_an_out_teammates_share_comes_only_from_games_before_the_target_game() -> None:
    early = [("B", 1, 0.3, 0.0, 0.8), ("B", 2, 0.3, 0.0, 0.8)]
    later_a = usage([*early, ("B", 3, 0.9, 0.5, 1.0), ("B", 4, 0.9, 0.5, 1.0)])
    later_b = usage([*early, ("B", 3, 0.0, 0.0, 0.0)])
    rep = report([("B", 3, "WR", "Out", "DNP")])
    a, b = features(rep, later_a), features(rep, later_b)
    assert a["vac_out_tgt"] == pytest.approx(0.3)
    assert {c: a[c] for c in vacancy.VAC_COLUMNS} == {c: b[c] for c in vacancy.VAC_COLUMNS}


def test_snaps_count_at_the_players_position_and_targets_across_the_team() -> None:
    use = usage([("B", 2, 0.2, 0.0, 0.9), ("C", 2, 0.1, 0.4, 0.7)])
    rep = report([("B", 3, "WR", "Doubtful", None), ("C", 3, "RB", "Out", None)])
    row = features(rep, use)
    assert row["vac_out_tgt"] == pytest.approx(0.3)
    assert row["vac_out_car"] == pytest.approx(0.4)
    assert row["vac_out_snap"] == pytest.approx(0.9)  # the back's snaps are not a receiver's


def test_a_questionable_teammate_counts_by_the_chance_he_sits_given_practice() -> None:
    use = usage([("B", 2, 0.2, 0.0, 0.5), ("C", 2, 0.1, 0.0, 0.5)])
    rep = report([("B", 3, "WR", "Questionable", "DNP"), ("C", 3, "WR", "Questionable", None)])
    row = features(rep, use)
    assert row["vac_q_tgt"] == pytest.approx(0.6 * 0.2 + 0.4 * 0.1)
    assert row["vac_out_tgt"] == 0.0


def test_the_player_himself_is_never_his_own_vacancy() -> None:
    use = usage([("A", 2, 0.25, 0.0, 0.9)])
    row = features(report([("A", 3, "WR", "Questionable", "Full")]), use)
    assert row["vac_q_tgt"] == 0.0 and row["vac_q_snap"] == 0.0


def test_an_out_teammate_above_him_on_the_chart_moves_him_up() -> None:
    chart = depth([("B", 3, 1.0), ("C", 3, 3.0)])
    rep = report([("B", 3, "WR", "Out", None), ("C", 3, "WR", "Out", None)])
    row = features(rep, usage([]), chart)
    assert row["eff_depth"] == 1.0  # B was above him; C below does not count


def test_no_report_gives_zero_vacancy_and_the_charts_rank() -> None:
    row = features(report([]), usage([("B", 2, 0.3, 0.0, 0.8)]))
    assert [row[c] for c in vacancy.VAC_COLUMNS] == [0.0] * 6 + [2.0]


def test_the_final_report_keeps_only_game_statuses_and_known_practice_labels() -> None:
    raw = pl.DataFrame(
        {
            "game_type": ["REG", "REG", "REG", "POST"],
            "team": ["KC"] * 4,
            "gsis_id": ["B", "C", "D", "E"],
            "position": ["WR"] * 4,
            "report_status": ["Out", "Note", None, "Out"],
            "practice_status": [
                "Did Not Participate In Practice",
                "Note",
                "Full Participation in Practice",
                None,
            ],
            "season": [2025] * 4,
            "week": [3] * 4,
        }
    )
    out = vacancy.report_table(raw).sort("gsis_id")
    assert out["status"].to_list() == ["Out", None, None]
    assert out["practice"].to_list() == ["DNP", None, "Full"]


def test_sleepers_out_status_stands_in_with_practice_unknown_and_nflverse_team_codes() -> None:
    players, id_map = sleeper(["Out", "Questionable", "IR", "Doubtful", None], list("BCDEF"))
    players = players.with_columns(pl.Series("team", ["LAR", "KC", "KC", "KC", "KC"]))
    out = vacancy.sleeper_report(players, id_map, 2025, 3)
    assert out.columns == list(REPORT)
    # Questionable and Doubtful are unreliable before the final report; IR is not a game status
    assert out["gsis_id"].to_list() == ["B"]
    assert out["status"].to_list() == ["Out"]
    assert out["team"].to_list() == ["LA"]
    assert out["practice"].null_count() == 1


def test_a_player_listed_twice_by_sleeper_stands_in_once() -> None:
    players, id_map = sleeper(["Out", "Out"], ["B", "B"])
    out = vacancy.sleeper_report(players, id_map, 2025, 3)
    assert out["gsis_id"].to_list() == ["B"]


def test_sleepers_unmapped_out_players_are_counted() -> None:
    players, id_map = sleeper(["Out", "Out", "Questionable"], ["B", None, None])
    assert vacancy.unmapped_out(players, id_map) == 1


def test_the_stand_in_and_the_report_give_the_same_features_for_the_same_statuses() -> None:
    use = usage([("B", 2, 0.2, 0.1, 0.9), ("C", 2, 0.1, 0.0, 0.6)])
    final = report([("B", 3, "WR", "Out", None)])
    players, id_map = sleeper(["Out", None], ["B", "C"])
    stand_in = vacancy.sleeper_report(players, id_map, 2025, 3)
    assert features(final, use) == features(stand_in, use)


STAND_IN = pl.DataFrame(
    [
        ("B", 2025, 3, "KC", "WR", "Out", None),
        ("C", 2025, 3, "KC", "WR", "Out", None),
        ("Y", 2025, 3, "BUF", "WR", "Out", None),
        ("Y", 2025, 3, "BUF", "WR", "Out", None),
    ],
    schema=REPORT,
    orient="row",
)
BUF_PRACTICE = pl.DataFrame(
    [("X", 2025, 3, "BUF", "WR", None, "Full")], schema=REPORT, orient="row"
)
THURSDAY = pl.DataFrame([("T", 2025, 3, "NE", "WR", "Out", "DNP")], schema=REPORT, orient="row")
GAMEDAYS = pl.DataFrame(
    {
        "season": [2025] * 3,
        "week": [3] * 3,
        "team": ["NE", "KC", "BUF"],
        "gameday": ["2025-09-18", "2025-09-21", "2025-09-21"],
    }
)


def buf_vacancy(rep: pl.DataFrame) -> float:
    use = usage([("Y", 2, 0.3, 0.2, 0.9)], team="BUF")
    target = targets("Z", 3).with_columns(pl.lit("BUF").alias("team"))
    return vacancy.vacancy_features(target, rep, use, WEIGHTS, depth([]))["vac_out_tgt"].item()


def test_once_a_slates_reports_are_out_a_team_on_it_with_no_game_status_is_healthy() -> None:
    final = pl.concat(
        [report([("B", 3, "WR", "Out", "DNP"), ("B", 2, "WR", "Out", "DNP")]), BUF_PRACTICE]
    )
    out = vacancy.with_stand_in(final, STAND_IN, GAMEDAYS, 2025, 3)
    assert out.sort("gsis_id", "week").equals(final.sort("gsis_id", "week"))  # no stand-in at all
    assert buf_vacancy(out) == 0.0  # Sleeper's Out on BUF is ignored
    sources = vacancy.report_sources(final, GAMEDAYS, 2025, 3, ["KC", "BUF"])
    assert sources == {"KC": "final", "BUF": "final"}


def test_a_thursday_report_does_not_publish_sundays_slate() -> None:
    final = pl.concat([THURSDAY, BUF_PRACTICE])
    out = vacancy.with_stand_in(final, STAND_IN, GAMEDAYS, 2025, 3)
    listed = out.filter((pl.col("week") == 3) & pl.col("status").is_not_null())
    assert sorted(listed["gsis_id"].to_list()) == ["B", "C", "T", "Y"]  # one row per player
    assert buf_vacancy(out) == pytest.approx(0.3)  # a Sunday team's Sleeper Out still counts
    sources = vacancy.report_sources(final, GAMEDAYS, 2025, 3, ["NE", "KC", "BUF"])
    assert sources == {"NE": "final", "KC": "sleeper", "BUF": "sleeper"}


def test_before_any_report_sleepers_out_list_stands_in_and_other_weeks_are_untouched() -> None:
    final = pl.concat([report([("B", 2, "WR", "Out", "DNP")]), BUF_PRACTICE])
    out = vacancy.with_stand_in(final, STAND_IN, GAMEDAYS, 2025, 3)
    listed = out.filter((pl.col("week") == 3) & pl.col("status").is_not_null())
    assert sorted(listed["gsis_id"].to_list()) == ["B", "C", "Y"]
    assert out.filter(pl.col("week") == 2).height == 1


def test_an_out_teammate_vacates_only_the_usage_he_had_with_this_team() -> None:
    traded = pl.concat(
        [usage([("B", 1, 0.3, 0.0, 0.9)], team="BUF"), usage([("B", 2, 0.1, 0.0, 0.4)])]
    )
    rep = report([("B", 3, "WR", "Out", None)])
    assert features(rep, traded)["vac_out_tgt"] == pytest.approx(0.1)
    only_buf = usage([("B", 1, 0.3, 0.0, 0.9)], team="BUF")
    assert features(rep, only_buf)["vac_out_tgt"] == 0.0


def test_no_questionable_history_gives_neutral_weights_with_a_warning(capsys) -> None:  # type: ignore[no-untyped-def]
    empty = pl.DataFrame(schema=REPORT)
    snaps = pl.DataFrame(schema={**KEY, "offense_snaps": pl.Float64})
    weights = vacancy.sit_weights(empty, snaps, 2023)
    assert weights == {None: 0.0}
    assert "WARNING" in capsys.readouterr().out
