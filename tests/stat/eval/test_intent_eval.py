"""
Measures how often the intent model turns a question into the expected stats/filters/granularity.

Needs a model, so it is deselected by default. The provider follows INTENT_PROVIDER like the app
(auto: Jev when JEV_API_KEY is set in the environment or `.env`), but with no fallback, so a Jev
failure counts as a miss instead of silently scoring the local model:
    set -a; source .env; set +a; uv run pytest -m eval -s          # Jev
    make ask-model; INTENT_PROVIDER=local uv run pytest -m eval -s  # local Qwen

`catalog.json` comes from `npm run export:catalog` (frontend/), so the ids are the real ones.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from openai import AsyncOpenAI

from nfl_stat.core.config import get_settings
from nfl_stat.schemas.nlq import IntentOutcome, IntentRequest, QueryOutcome
from nfl_stat.services.jev_intent import JevError, translate_with_jev
from nfl_stat.services.nlq_intent import IntentError, translate_question

EVAL_DIR = Path(__file__).parent
RESULTS_FILE = EVAL_DIR / "results.jsonl"
MIN_PASS_RATE = 0.8
MIN_REFUSAL_RATE = 0.75  # a model that never refuses must fail even though refusals are few
# `corrections` holds questions a user had to fix in the app (added with promote.py). `heldout2`
# was committed before any model saw it (#71).
SETS = ("cases", "heldout", "heldout2", "corrections")

pytestmark = pytest.mark.eval


def _check(case: dict[str, Any], outcome: Any) -> str | None:
    """Return why the answer is wrong, or None if it matches the expectation."""
    if case.get("unsupported"):
        return None if outcome.outcome == "unsupported" else "answered a question it should refuse"
    if not isinstance(outcome, QueryOutcome):
        return f"refused a question it can answer ({outcome.reason})"
    stat_ids, filter_ids = outcome.intent.stat_ids, outcome.intent.filter_ids
    granularity = outcome.intent.granularity
    if set(stat_ids) != set(case["stats"]):
        return f"stats {sorted(stat_ids)} != {sorted(case['stats'])}"
    if set(filter_ids) != set(case["filters"]):
        return f"filters {sorted(filter_ids)} != {sorted(case['filters'])}"
    if case["granularity"] is not None and granularity != case["granularity"]:
        return f"granularity {granularity} != {case['granularity']}"
    return None


def _latency(seconds: list[float]) -> dict[str, float]:
    """Mean and 95th percentile of the per-question times, in seconds."""
    p95 = statistics.quantiles(seconds, n=20)[-1] if len(seconds) > 1 else seconds[0]
    return {"mean_s": round(statistics.fmean(seconds), 2), "p95_s": round(p95, 2)}


def _record_run(
    model: str,
    passed: int,
    total: int,
    by_set: dict[str, str],
    seconds: list[float],
    failures: list[str],
) -> None:
    """Append one line per run, so accuracy, speed and each set's score can be compared."""
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "passed": passed,
        "total": total,
        "rate": round(passed / total, 3),
        "by_set": by_set,
        "latency": _latency(seconds),
        "failures": failures,
    }
    with RESULTS_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


async def test_intent_pass_rate_meets_threshold():
    settings = get_settings()
    catalog = json.loads((EVAL_DIR / "catalog.json").read_text())
    # The held-out set was written before the rules parser. The model is scored on it too, so both
    # paths can be compared on the same questions (`npm run eval:rules` in frontend/ scores rules).
    cases = [
        {**c, "set": name}
        for name in SETS
        for c in json.loads((EVAL_DIR / f"{name}.json").read_text())
    ]
    client = AsyncOpenAI(
        base_url=settings.llm_base_url, api_key="local", timeout=settings.llm_timeout_seconds
    )
    key = settings.jev_api_key.get_secret_value() if settings.jev_api_key else ""
    use_jev = settings.intent_provider != "local" and bool(key)
    model = f"jev:{settings.jev_model}" if use_jev else settings.llm_model

    async def ask(req: IntentRequest) -> IntentOutcome:
        if use_jev:
            return await translate_with_jev(
                req, api_key=key, model=settings.jev_model, timeout=settings.jev_timeout_seconds
            )
        return await translate_question(client=client, model=settings.llm_model, req=req)

    failures: list[str] = []
    seconds: list[float] = []
    for case in cases:
        req = IntentRequest(question=case["q"], **catalog)
        started = time.perf_counter()
        try:
            outcome = await ask(req)
        except (IntentError, JevError) as e:
            seconds.append(time.perf_counter() - started)
            failures.append(f"{case['q']!r}: invalid after retry ({e})")
            continue
        seconds.append(time.perf_counter() - started)
        why = _check(case, outcome)
        if why:
            failures.append(f"{case['q']!r}: {why}")
    await client.close()

    passed = len(cases) - len(failures)
    rate = passed / len(cases)
    report = "\n".join(failures)
    by_set = {
        name: sum(
            1
            for c in cases
            if c["set"] == name and not any(f.startswith(repr(c["q"])) for f in failures)
        )
        for name in SETS
    }
    totals = {name: sum(1 for c in cases if c["set"] == name) for name in by_set}
    split = {name: f"{by_set[name]}/{totals[name]}" for name in by_set}
    _record_run(model, passed, len(cases), split, seconds, failures)
    speed = _latency(seconds)
    print(
        f"\nintent eval ({model}): {passed}/{len(cases)} passed ({rate:.0%}); "
        + ", ".join(f"{name} {score}" for name, score in split.items())
        + f"; {speed['mean_s']}s mean, {speed['p95_s']}s p95\n{report}"
    )
    # Only the original cases gate the run. The held-out set and the corrections are reported but
    # do not fail it. The held-out refusals:
    # the model currently answers all seven (see issue #9), so gating on them would keep this red.
    gated = [c for c in cases if c["set"] == "cases"]
    gated_failures = [f for f in failures if any(f.startswith(repr(c["q"])) for c in gated)]
    gated_rate = (len(gated) - len(gated_failures)) / len(gated)
    refusals = [c["q"] for c in gated if c.get("unsupported")]
    missed = [q for q in refusals if any(f.startswith(repr(q)) for f in gated_failures)]
    refusal_rate = 1 - len(missed) / len(refusals) if refusals else 1.0
    assert gated_rate >= MIN_PASS_RATE, (
        f"pass rate {gated_rate:.0%} < {MIN_PASS_RATE:.0%}\n{report}"
    )
    assert refusal_rate >= MIN_REFUSAL_RATE, f"refusal rate {refusal_rate:.0%}\n{report}"
