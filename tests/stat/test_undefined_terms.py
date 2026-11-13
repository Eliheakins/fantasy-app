from __future__ import annotations

import httpx2
import pytest

from nfl_stat.schemas.nlq import CatalogStat, IntentRequest, UnsupportedOutcome
from nfl_stat.services.jev_intent import translate_with_jev
from nfl_stat.services.undefined_terms import undefined_term


@pytest.mark.parametrize(
    "question",
    [
        "Derrick Henry rush yards over expected 2024",
        "George Kittle YAC over expected 2024",
        "Brian Thomas yards per route run",
        "Jets pass rush pressure rate",
        "Travis Kelce snap share 2025",
    ],
)
def test_terms_the_catalog_lacks_are_refused(question: str):
    assert undefined_term(question) is not None


@pytest.mark.parametrize(
    "question",
    [
        "Mahomes passing yards 2025",
        "Burrow CPOE 2024",
        "Derrick Henry expected rush yards 2024",
        "Josh Allen hit to sack rate 2024",
    ],
)
def test_defined_terms_pass(question: str):
    assert undefined_term(question) is None


async def test_jev_is_not_asked_about_an_undefined_term():
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("Jev must not be called")

    req = IntentRequest(
        question="Derrick Henry RYOE 2024",
        stats=[CatalogStat(id="rush_yards", label="Rush yards", category="rushing")],
    )

    outcome = await translate_with_jev(
        req, api_key="k", model="m", timeout=1, transport=httpx2.MockTransport(fail)
    )

    assert isinstance(outcome, UnsupportedOutcome)
    assert "over expected" in outcome.reason
