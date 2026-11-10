from __future__ import annotations

import json
from typing import cast

import pytest
from fakes import FILTERS, STATS, FakeLlm
from openai import AsyncOpenAI
from pydantic import ValidationError

from nfl_stat.schemas.nlq import CatalogStat, IntentRequest, QueryOutcome, UnsupportedOutcome
from nfl_stat.services.nlq_intent import (
    IntentError,
    build_system_prompt,
    extract_json_object,
    parse_intent,
    parse_reply,
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
    intent = _parse(json.dumps({"stat_ids": [*many, "pass_yards"]}))

    assert intent.stat_ids == ["pass_yards", "pass_tds", "rec_yards", "rec_receptions", "eff_epa"]


def test_system_prompt_lists_catalog_and_only_examples_with_known_ids():
    prompt = build_system_prompt(STATS, FILTERS)

    assert "rec_yards | Rec yards | receiving" in prompt
    assert (
        "pass_yards | Pass yards | passing | also called: passing yards, yards through the air"
        in prompt
    )
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

    outcome = await translate_question(client=cast(AsyncOpenAI, llm), model="m", req=req)

    assert isinstance(outcome, QueryOutcome)
    assert outcome.intent.stat_ids == ["rec_yards"]
    assert outcome.intent.granularity == "per_game"
    retry_messages = llm.calls[1]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"stat_ids": ["nope"]}'}
    assert "Unknown stat_ids" in retry_messages[-1]["content"]


async def test_translate_question_returns_unsupported_without_a_retry():
    llm = FakeLlm(['{"unsupported": "That is an opinion, not a stat."}'])
    req = IntentRequest(question="Is Mahomes better than Brady?", stats=STATS, filters=FILTERS)

    outcome = await translate_question(client=cast(AsyncOpenAI, llm), model="m", req=req)

    assert outcome == UnsupportedOutcome(reason="That is an opinion, not a stat.")
    assert len(llm.calls) == 1


def test_parse_reply_treats_a_blank_reason_as_an_invalid_reply():
    with pytest.raises(IntentError, match="reason"):
        parse_reply('{"unsupported": "  "}', stat_ids=STAT_IDS, filter_ids=FILTER_IDS)


def test_parse_reply_ignores_stats_when_the_model_says_unsupported():
    reply = '{"unsupported": "No salary data.", "stat_ids": ["pass_yards"]}'

    outcome = parse_reply(reply, stat_ids=STAT_IDS, filter_ids=FILTER_IDS)

    assert isinstance(outcome, UnsupportedOutcome)


def test_a_stat_line_cannot_be_split_by_newlines_in_an_alias():
    stat = CatalogStat(id="pass_yards", label="Pass yards", category="passing", aliases=["a\nb\tc"])

    prompt = build_system_prompt([stat], FILTERS)

    assert "also called: a b c" in prompt


def test_the_catalog_sent_by_the_client_is_bounded():
    too_many_aliases = {"id": "x", "label": "X", "category": "c", "aliases": ["a"] * 21}
    long_alias = {"id": "x", "label": "X", "category": "c", "aliases": ["a" * 61]}
    base = {"question": "q", "filters": []}

    for stat in (too_many_aliases, long_alias):
        with pytest.raises(ValidationError):
            IntentRequest.model_validate({**base, "stats": [stat]})
    with pytest.raises(ValidationError):
        IntentRequest.model_validate(
            {**base, "stats": [{"id": "x", "label": "X", "category": "c"}] * 201}
        )
    with pytest.raises(ValidationError):
        IntentRequest.model_validate(
            {
                "question": "q",
                "stats": [{"id": "x", "label": "X", "category": "c"}],
                "filters": [{"id": "f", "label": "F", "group": "G"}] * 401,
            }
        )


@pytest.mark.parametrize("flag", ["null", "false"])
def test_parse_reply_treats_an_empty_unsupported_flag_as_absent(flag: str):
    reply = '{"unsupported": ' + flag + ', "stat_ids": ["pass_yards"]}'

    outcome = parse_reply(reply, stat_ids=STAT_IDS, filter_ids=FILTER_IDS)

    assert isinstance(outcome, QueryOutcome)
    assert outcome.intent.stat_ids == ["pass_yards"]


def test_system_prompt_tells_the_model_how_to_refuse():
    prompt = build_system_prompt(STATS, FILTERS)

    assert '{"unsupported":' in prompt


async def test_translate_question_raises_after_two_invalid_replies():
    llm = FakeLlm(["not json", "still not json"])
    req = IntentRequest(question="anything", stats=STATS, filters=FILTERS)

    with pytest.raises(IntentError):
        await translate_question(client=cast(AsyncOpenAI, llm), model="m", req=req)

    assert len(llm.calls) == 2
