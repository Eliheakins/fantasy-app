"""
Measures how often the local model turns a question into the expected stats/filters/granularity.

Needs the model server running, so it is deselected by default:
    uv run --group llm mlx_lm.server --model mlx-community/Qwen2.5-14B-Instruct-4bit --port 8080
    uv run pytest -m eval -s

`catalog.json` comes from `npm run export:catalog` (frontend/), so the ids are the real ones.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from openai import AsyncOpenAI

from core.config import get_settings
from schemas.nlq import IntentRequest
from services.nlq_intent import IntentError, translate_question

EVAL_DIR = Path(__file__).parent
RESULTS_FILE = EVAL_DIR / "results.jsonl"
MIN_PASS_RATE = 0.8

pytestmark = pytest.mark.eval


def _check(
    case: dict[str, Any], stat_ids: list[str], filter_ids: list[str], granularity: str
) -> str | None:
    """Return why the answer is wrong, or None if it matches the expectation."""
    if set(stat_ids) != set(case["stats"]):
        return f"stats {sorted(stat_ids)} != {sorted(case['stats'])}"
    if set(filter_ids) != set(case["filters"]):
        return f"filters {sorted(filter_ids)} != {sorted(case['filters'])}"
    if case["granularity"] is not None and granularity != case["granularity"]:
        return f"granularity {granularity} != {case['granularity']}"
    return None


def _record_run(model: str, passed: int, total: int, failures: list[str]) -> None:
    """Append one line per run, so accuracy per model can be compared over time."""
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "passed": passed,
        "total": total,
        "rate": round(passed / total, 3),
        "failures": failures,
    }
    with RESULTS_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


async def test_intent_pass_rate_meets_threshold():
    settings = get_settings()
    catalog = json.loads((EVAL_DIR / "catalog.json").read_text())
    cases = json.loads((EVAL_DIR / "cases.json").read_text())
    client = AsyncOpenAI(
        base_url=settings.llm_base_url, api_key="local", timeout=settings.llm_timeout_seconds
    )

    failures: list[str] = []
    for case in cases:
        req = IntentRequest(question=case["q"], **catalog)
        try:
            intent = await translate_question(client=client, model=settings.llm_model, req=req)
        except IntentError as e:
            failures.append(f"{case['q']!r}: invalid after retry ({e})")
            continue
        why = _check(case, intent.stat_ids, intent.filter_ids, intent.granularity)
        if why:
            failures.append(f"{case['q']!r}: {why}")
    await client.close()

    passed = len(cases) - len(failures)
    rate = passed / len(cases)
    _record_run(settings.llm_model, passed, len(cases), failures)
    report = "\n".join(failures)
    print(f"\nintent eval: {passed}/{len(cases)} passed ({rate:.0%})\n{report}")
    assert rate >= MIN_PASS_RATE, f"pass rate {rate:.0%} < {MIN_PASS_RATE:.0%}\n{report}"
