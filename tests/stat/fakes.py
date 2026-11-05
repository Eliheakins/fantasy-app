"""Shared stat-test doubles: the catalog the intent tests use and a scripted fake LLM client."""

from types import SimpleNamespace
from typing import Any

from nfl_stat.schemas.nlq import CatalogFilter, CatalogStat

STATS = [
    CatalogStat(
        id="pass_yards",
        label="Pass yards",
        category="passing",
        aliases=["passing yards", "yards through the air"],
    ),
    CatalogStat(id="pass_tds", label="Pass TDs", category="passing"),
    CatalogStat(id="rec_yards", label="Rec yards", category="receiving"),
    CatalogStat(id="rec_receptions", label="Receptions", category="receiving"),
    CatalogStat(id="eff_epa", label="EPA/Play", category="efficiency"),
]
FILTERS = [
    CatalogFilter(id="season-2023", label="2023", group="Season"),
    CatalogFilter(id="season-2022", label="2022", group="Season"),
    CatalogFilter(id="stype-post", label="Playoffs", group="Season type"),
    CatalogFilter(id="down-3", label="3rd", group="Down"),
]


class FakeLlm:
    """Stands in for AsyncOpenAI: returns scripted replies and records the messages it saw."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict[str, Any]]] = []
        self.base_url = "http://fake-llm/v1"
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, messages: list[dict[str, Any]], **_: Any) -> Any:
        self.calls.append(messages)
        content = self._replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
