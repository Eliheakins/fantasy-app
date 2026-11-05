from __future__ import annotations

import json
from pathlib import Path

import pytest
from promote import PromoteError, main, promote

CATALOG = {
    "stats": [{"id": "pass_yards"}, {"id": "rush_yards"}, {"id": "ypc"}],
    "filters": [{"id": "season-2023"}, {"id": "stype-reg"}],
}


def case(q: str, stats: list[str] | None = None, filters: list[str] | None = None) -> dict:
    return {
        "q": q,
        "stats": stats or ["pass_yards"],
        "filters": filters or ["season-2023"],
        "granularity": "total",
    }


def test_appends_a_valid_correction_after_the_existing_ones():
    existing = {"cases": [], "heldout": [], "corrections": [case("Old question")]}

    added, skipped = promote([case("Mahomes passing yards in 2023")], existing, CATALOG)

    assert added == [case("Mahomes passing yards in 2023")]
    assert skipped == []


def test_skips_questions_already_in_any_set_ignoring_case_and_spacing():
    existing = {"cases": [case("Mahomes passing yards in 2023")], "heldout": [], "corrections": []}

    added, skipped = promote([case("  mahomes  PASSING yards in 2023 ")], existing, CATALOG)

    assert added == []
    assert skipped == ["'  mahomes  PASSING yards in 2023 ': already in an eval set"]


def test_flags_a_skipped_question_whose_expected_answer_differs():
    existing = {"cases": [case("Chubb ypc", ["ypc"])], "heldout": [], "corrections": []}

    _, skipped = promote([case("Chubb ypc", ["rush_yards"])], existing, CATALOG)

    assert skipped == ["'Chubb ypc': already in an eval set, with a different expected answer"]


def test_keeps_only_the_first_of_a_question_exported_twice():
    added, _ = promote(
        [case("Chubb ypc", ["ypc"]), case("chubb ypc", ["rush_yards"])],
        {"cases": [], "heldout": [], "corrections": []},
        CATALOG,
    )

    assert [c["stats"] for c in added] == [["ypc"]]


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (case("Q", stats=["net_yards"]), "unknown stat 'net_yards'"),
        (case("Q", filters=["opp-KC"]), "unknown filter 'opp-KC'"),
        ({**case("Q"), "granularity": "per_drive"}, "granularity"),
        ({**case("Q"), "stats": []}, "stats"),
        ({"stats": ["pass_yards"], "filters": [], "granularity": "total"}, "q"),
    ],
)
def test_rejects_a_case_the_eval_could_not_score(bad: dict, message: str):
    with pytest.raises(PromoteError, match=message):
        promote([bad], {"cases": [], "heldout": [], "corrections": []}, CATALOG)


def test_rejects_an_export_that_is_not_a_list():
    with pytest.raises(PromoteError, match="list"):
        promote({"q": "Q"}, {"cases": [], "heldout": [], "corrections": []}, CATALOG)


def _eval_dir(tmp_path: Path) -> Path:
    (tmp_path / "catalog.json").write_text(json.dumps(CATALOG))
    for name in ("cases", "heldout", "heldout2", "corrections"):
        (tmp_path / f"{name}.json").write_text("[]")
    return tmp_path


def test_main_writes_the_new_corrections(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    eval_dir = _eval_dir(tmp_path)
    export = tmp_path / "export.json"
    export.write_text(json.dumps([case("Mahomes passing yards in 2023")]))

    code = main([str(export)], eval_dir=eval_dir)

    assert code == 0
    assert json.loads((eval_dir / "corrections.json").read_text()) == [
        case("Mahomes passing yards in 2023")
    ]
    assert "added 1" in capsys.readouterr().out


def test_main_leaves_the_set_untouched_on_a_bad_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    eval_dir = _eval_dir(tmp_path)
    export = tmp_path / "export.json"
    export.write_text("not json")

    code = main([str(export)], eval_dir=eval_dir)

    assert code == 1
    assert (eval_dir / "corrections.json").read_text() == "[]"
    assert "export.json" in capsys.readouterr().err
