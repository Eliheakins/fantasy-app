import polars as pl
import pytest

from fantasy.stages import vacancy

KEY = {"gsis_id": pl.String, "season": pl.Int64, "week": pl.Int64}
REPORT = {**KEY, "team": pl.String, "position": pl.String, "status": pl.String,
          "practice": pl.String}  # fmt: skip
WEIGHTS = {"Full": 0.25, "Limited": 0.35, "DNP": 0.6, None: 0.4}


def usage(rows: list[tuple[str, int, float, float, float]]) -> pl.DataFrame:
    """(player, week, target share, carry share, snap share) in 2025."""
    return pl.DataFrame(
        [(g, 2025, w, t, c, s) for g, w, t, c, s in rows],
        schema={**KEY, "tgt": pl.Float64, "car": pl.Float64, "snap": pl.Float64},
        orient="row",
    )


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


def test_sleepers_status_maps_to_the_reports_categories_with_practice_unknown() -> None:
    players = pl.DataFrame(
        {
            "sleeper_id": ["1", "2", "3", "4", "5"],
            "position": ["WR", "RB", "TE", "WR", "WR"],
            "team": ["KC", "LAR", "KC", "KC", "KC"],
            "injury_status": ["Out", "Questionable", "IR", "Doubtful", None],
        }
    )
    id_map = pl.DataFrame({"sleeper_id": ["1", "2", "3", "4", "5"], "gsis_id": list("BCDEF")})
    out = vacancy.sleeper_report(players, id_map, 2025, 3).sort("gsis_id")
    assert out.columns == list(REPORT)
    assert out["gsis_id"].to_list() == ["B", "C", "E"]  # IR is not a game status
    assert out["status"].to_list() == ["Out", "Questionable", "Doubtful"]
    assert out["team"].to_list() == ["KC", "LA", "KC"]  # nflverse team codes
    assert out["practice"].null_count() == 3


def test_the_stand_in_and_the_report_give_the_same_features_for_the_same_statuses() -> None:
    use = usage([("B", 2, 0.2, 0.1, 0.9), ("C", 2, 0.1, 0.0, 0.6)])
    final = report([("B", 3, "WR", "Out", None), ("C", 3, "WR", "Questionable", None)])
    players = pl.DataFrame(
        {"sleeper_id": ["1", "2"], "position": ["WR", "WR"], "team": ["KC", "KC"],
         "injury_status": ["Out", "Questionable"]}
    )  # fmt: skip
    stand_in = vacancy.sleeper_report(
        players, pl.DataFrame({"sleeper_id": ["1", "2"], "gsis_id": ["B", "C"]}), 2025, 3
    )
    assert features(final, use) == features(stand_in, use)


def test_a_teams_week_uses_the_final_report_once_it_has_game_statuses_else_the_stand_in() -> None:
    final = pl.concat(
        [
            report([("B", 3, "WR", "Out", "DNP")]),
            pl.DataFrame([("X", 2025, 3, "BUF", "WR", None, "Full")], schema=REPORT, orient="row"),
        ]
    )
    stand_in = pl.DataFrame(
        [("C", 2025, 3, "KC", "WR", "Out", None), ("Y", 2025, 3, "BUF", "WR", "Out", None)],
        schema=REPORT,
        orient="row",
    )
    out = vacancy.with_stand_in(final, stand_in, 2025, 3).sort("gsis_id")
    # KC has a game status on the final report; BUF has only a practice row, so Sleeper's is used
    assert out.filter(pl.col("week") == 3)["gsis_id"].to_list() == ["B", "Y"]
