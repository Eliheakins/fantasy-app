from __future__ import annotations

import json

import pytest
from conftest import FILTERS, STATS, FakeLlm

from schemas.nlq import IntentRequest
from services.nlq_intent import (
    IntentError,
    build_system_prompt,
    extract_json_object,
    parse_intent,
    translate_question,
)

STAT_IDS = {s.id for s in STATS}
FILTER_IDS = {f.id for f in FILTERS}


def _parse(text: str):
    return parse_intent(text, stat_ids=STAT_IDS, filter_ids=FILTER_IDS)


def test_extract_json_object_strips_fences_and_trailing_prose():
    text = '```json\n{"stat_ids": ["pass_yards"]}\n```\nHope that helps!'
    assert extract_json_object(text) == {"stat_ids": ["pass_yards"]}


def test_extract_json_object_raises_when_no_object():
    with pytest.raises(IntentError, match="No JSON object"):
        extract_json_object("I cannot answer that.")


def test_extract_json_object_raises_on_malformed_json():
    with pytest.raises(IntentError, match="Invalid JSON"):
        extract_json_object('{"stat_ids": [pass_yards}')


def test_parse_intent_accepts_valid_reply_and_defaults_granularity():
    intent = _parse('{"stat_ids": ["pass_yards"], "filter_ids": ["season-2023"]}')

    assert intent.stat_ids == ["pass_yards"]
    assert intent.filter_ids == ["season-2023"]
    assert intent.granularity == "total"


def test_parse_intent_rejects_unknown_stat_id():
    with pytest.raises(IntentError, match="Unknown stat_ids"):
        _parse('{"stat_ids": ["made_up_stat"]}')


def test_parse_intent_rejects_unknown_filter_id():
    with pytest.raises(IntentError, match="Unknown filter_ids"):
        _parse('{"stat_ids": ["pass_yards"], "filter_ids": ["season-1999"]}')


def test_parse_intent_rejects_bad_granularity():
    with pytest.raises(IntentError, match="Wrong shape"):
        _parse('{"stat_ids": ["pass_yards"], "granularity": "weekly"}')


def test_parse_intent_rejects_empty_stat_list():
    with pytest.raises(IntentError, match="Wrong shape"):
        _parse('{"stat_ids": []}')


def test_parse_intent_dedupes_and_caps_stats_at_five():
    many = ["pass_yards", "pass_yards", "pass_tds", "rec_yards", "rec_receptions", "eff_epa"]
    intent = _parse(json.dumps({"stat_ids": many + ["pass_yards"]}))

    assert intent.stat_ids == ["pass_yards", "pass_tds", "rec_yards", "rec_receptions", "eff_epa"]


def test_system_prompt_lists_catalog_and_only_examples_with_known_ids():
    prompt = build_system_prompt(STATS, FILTERS)

    assert "rec_yards | Rec yards | receiving" in prompt
    assert "season-2023 | Season: 2023" in prompt
    # Uses pass_yards/pass_tds/season-2023, all present in the test catalog.
    assert "Mahomes passing yards" in prompt
    # Needs rush_yards, which the test catalog lacks.
    assert "Derrick Henry" not in prompt


async def test_translate_question_retries_once_with_the_error_then_succeeds():
    llm = FakeLlm(
        ['{"stat_ids": ["nope"]}', '{"stat_ids": ["rec_yards"], "granularity": "per_game"}']
    )
    req = IntentRequest(question="Kelce yards per game", stats=STATS, filters=FILTERS)

    intent = await translate_question(client=llm, model="m", req=req)

    assert intent.stat_ids == ["rec_yards"]
    assert intent.granularity == "per_game"
    retry_messages = llm.calls[1]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"stat_ids": ["nope"]}'}
    assert "Unknown stat_ids" in retry_messages[-1]["content"]


async def test_translate_question_raises_after_two_invalid_replies():
    llm = FakeLlm(["not json", "still not json"])
    req = IntentRequest(question="anything", stats=STATS, filters=FILTERS)

    with pytest.raises(IntentError):
        await translate_question(client=llm, model="m", req=req)

    assert len(llm.calls) == 2
