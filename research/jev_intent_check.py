"""
Scores Jev (TypeSafe's System One model) on Ask's intent eval sets, for issue #71.

Same cases and the same pass rule as tests/stat/eval/test_intent_eval.py, so the result compares
with the local Qwen run. Jev answers typed questions instead of writing JSON, so one request per
question carries: a Noul per stat, a Noul per non-season filter, a Choice for granularity, and
three companion Nouls for "the catalog cannot answer this". Seasons are read in code (Jev is weak
at numbers and dates): explicit years by regex, relative phrases by a Choice that code maps to a
year. Only the question text and the generic catalog are sent; no league data.

    set -a; source .env; set +a   # JEV_API_KEY
    uv run python research/jev_intent_check.py [--reverse-choice] [--out results.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import ssl
import statistics
import time
from pathlib import Path
from typing import Any

import httpx2

EVAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "stat" / "eval"
SETS = ("cases", "heldout", "corrections")
URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
CURRENT_SEASON = 2026
MAX_STATS = 5
THRESHOLD = 0.5  # fixed before the run; the probabilities are saved, so others can be scored later
CONCURRENCY = 2

GROUP_PHRASE = {
    "Down": "plays on {label} down",
    "Distance to go": "plays with {label} yards to go",
    "Week": "{label} weeks of the season",
    "Location": "{label} games",
    "Field position": "plays in the {label}",
    "Red zone (flag)": "red zone plays",
    "Goal to go": "goal-to-go plays",
    "Season type": "the {label}",
    "Quarter": "the {label} quarter",
    "Game clock": "the {label}",
    "Game state": "plays while the team is {label}",
    "Offense personnel": "plays in {label} offensive personnel",
    "Defenders in box": "plays against a {label} defensive box",
    "Pass rushers": "plays with {label}",
    "Weather": "games with {label}",
}

GRANULARITY = {
    "total": "Season or game totals; the question does not ask for a per game or per play rate.",
    "per_game": "The question asks for an average per game.",
    "per_play": "The question asks per play, per attempt, per carry, per target, or for an "
    "efficiency rate.",
}

SEASON_REF = {
    "none": "The question names no season, or names a season by its year.",
    "this_season": "The question says this season, this year or the current season.",
    "last_season": "The question says last season or last year.",
    "two_seasons_ago": "The question says two seasons ago or two years ago.",
}
SEASON_OFFSET = {"this_season": 0, "last_season": 1, "two_seasons_ago": 2}


def build_questions(catalog: dict[str, Any], reverse_choice: bool, version: int) -> dict[str, Any]:
    stats, filters = catalog["stats"], catalog["filters"]
    stat_list = "; ".join(s["label"] for s in stats)
    situation_list = "; ".join(
        f"{f['group']}: {f['label']}" for f in filters if f["group"] != "Season"
    )
    questions: dict[str, Any] = {}
    for s in stats:
        also = f" Also called: {', '.join(s['aliases'])}." if s.get("aliases") else ""
        questions[f"stat__{s['id']}"] = {
            "type": "noul",
            "instructions": f"Does the question ask for the NFL statistic '{s['label']}' "
            f"({s['category']})?{also}",
            "criteria": {
                "true": f"The question asks for {s['label']} or one of its other names.",
                "false": "The question asks for a different statistic, or none.",
            },
        }
    for f in filters:
        if f["group"] == "Season":
            continue
        phrase = GROUP_PHRASE.get(f["group"], "{label}").format(label=f["label"])
        questions[f"filter__{f['id']}"] = {
            "type": "noul",
            "instructions": f"Does the question limit the statistics to {phrase} "
            f"({f['group']}: {f['label']})?",
        }
    gran = dict(reversed(GRANULARITY.items())) if reverse_choice else GRANULARITY
    questions["granularity"] = {
        "type": "choice",
        "instructions": "Does the question ask for totals, a per game average, or a per play rate?",
        "criteria": gran,
    }
    ref = dict(reversed(SEASON_REF.items())) if reverse_choice else SEASON_REF
    questions["season_ref"] = {
        "type": "choice",
        "instructions": "How does the question refer to the NFL season?",
        "criteria": ref,
    }
    if version == 1:
        questions["gap_stat"] = {
            "type": "noul",
            "instructions": "Does the question ask for something that is not one of these NFL "
            f"statistics: {stat_list}? Salaries, awards, championships, team records, opinions "
            "such as who is better, and combined or differently defined statistics are not on "
            "the list.",
        }
        questions["gap_condition"] = {
            "type": "noul",
            "instructions": "Does the question limit the statistics by a condition that is not a "
            f"season, a player, or one of these situations: {situation_list}? Opponents and "
            "time left in the game are examples of conditions not on the list.",
        }
    else:
        questions["has_condition"] = {
            "type": "noul",
            "instructions": "Does the question limit the statistics to some situation or "
            "condition, such as a down, a quarter, a part of the field, the score, the weather, "
            "the opponent or the time left in a game? A season, a player, and per game or per "
            "play wording do not count.",
        }
        questions["multi_stat"] = {
            "type": "noul",
            "instructions": "Does the question ask for two or more different statistics?",
        }
    questions["leaderboard"] = {
        "type": "noul",
        "instructions": "Does the question ask which player leads or ranks first, without naming "
        "the player it is about?",
    }
    return questions


def to_outcome(
    answers: dict[str, Any], question: str, catalog: dict[str, Any], version: int
) -> dict[str, Any]:
    seasons = {f["id"] for f in catalog["filters"] if f["group"] == "Season"}
    years = re.findall(r"\b(19\d\d|20\d\d)\b", question)
    if any(f"season-{y}" not in seasons for y in years):
        return {"outcome": "unsupported", "reason": "season outside the data"}
    companions = ("gap_stat", "gap_condition", "leaderboard") if version == 1 else ("leaderboard",)
    if max(answers[k]["noul"] for k in companions) > THRESHOLD:
        return {"outcome": "unsupported", "reason": "companion noul"}
    stat_p = {
        k.removeprefix("stat__"): a["noul"] for k, a in answers.items() if k.startswith("stat__")
    }
    picked = [s for s, p in sorted(stat_p.items(), key=lambda kv: -kv[1]) if p > THRESHOLD]
    if not picked:
        return {"outcome": "unsupported", "reason": "no stat above threshold"}
    if version == 2 and answers["multi_stat"]["noul"] <= THRESHOLD:
        picked = picked[:1]
    filters = [
        k.removeprefix("filter__")
        for k, a in answers.items()
        if k.startswith("filter__") and a["noul"] > THRESHOLD
    ]
    if version == 2 and answers["has_condition"]["noul"] > THRESHOLD and not filters:
        return {"outcome": "unsupported", "reason": "a condition no filter covers"}
    filters += [f"season-{y}" for y in years]
    ref = answers["season_ref"]["choice"]
    if not years and ref in SEASON_OFFSET:
        filters.append(f"season-{CURRENT_SEASON - SEASON_OFFSET[ref]}")
    return {
        "outcome": "query",
        "stat_ids": picked[:MAX_STATS],
        "filter_ids": sorted(set(filters)),
        "granularity": answers["granularity"]["choice"],
    }


def check(case: dict[str, Any], out: dict[str, Any]) -> str | None:
    """The pass rule of tests/stat/eval/test_intent_eval.py::_check."""
    if case.get("unsupported"):
        return None if out["outcome"] == "unsupported" else "answered a question it should refuse"
    if out["outcome"] != "query":
        return f"refused a question it can answer ({out['reason']})"
    if set(out["stat_ids"]) != set(case["stats"]):
        return f"stats {sorted(out['stat_ids'])} != {sorted(case['stats'])}"
    if set(out["filter_ids"]) != set(case["filters"]):
        return f"filters {sorted(out['filter_ids'])} != {sorted(case['filters'])}"
    if case["granularity"] is not None and out["granularity"] != case["granularity"]:
        return f"granularity {out['granularity']} != {case['granularity']}"
    return None


async def ask(headers: dict[str, str], sem: asyncio.Semaphore, question: str,
              questions: dict[str, Any]) -> tuple[dict[str, Any], float, dict[str, Any]]:
    async with sem:
        started = time.perf_counter()
        for attempt in range(5):
            try:
                # a fresh connection per request: reused TLS connections failed with bad record mac
                async with httpx2.AsyncClient(headers=headers, timeout=60) as client:
                    r = await client.post(URL, json={"model": MODEL,
                                                     "state": {"question": question},
                                                     "questions": questions})
            except (httpx2.TransportError, ssl.SSLError):
                if attempt == 4:
                    raise
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code not in (429, 502, 503, 504):
                break
            await asyncio.sleep(float(r.headers.get("retry-after", 2 ** attempt)))
        r.raise_for_status()
        body = r.json()
        return body["answers"], time.perf_counter() - started, body.get("usage", {}) | {
            "model": body.get("model")}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reverse-choice", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--version", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    key = os.environ.get("JEV_API_KEY")
    if not key:
        raise SystemExit("JEV_API_KEY is not set (source .env first)")
    catalog = json.loads((EVAL_DIR / "catalog.json").read_text())
    cases = [{**c, "set": n} for n in SETS for c in json.loads((EVAL_DIR / f"{n}.json").read_text())]
    questions = build_questions(catalog, args.reverse_choice, args.version)
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"Authorization": f"Bearer {key}"}
    results = await asyncio.gather(*(ask(headers, sem, c["q"], questions) for c in cases))
    rows, seconds, tokens, failures = [], [], 0, []
    for case, (answers, secs, usage) in zip(cases, results, strict=True):
        out = to_outcome(answers, case["q"], catalog, args.version)
        why = check(case, out)
        seconds.append(secs)
        tokens += usage.get("input_tokens", 0)
        rows.append({"case": case, "outcome": out, "why": why, "seconds": secs,
                     "answers": answers, "model": usage.get("model")})
        if why:
            failures.append(f"[{case['set']}] {case['q']!r}: {why}")
    by_set = {
        n: f"{sum(1 for r in rows if r['case']['set'] == n and not r['why'])}/"
        f"{sum(1 for r in rows if r['case']['set'] == n)}"
        for n in SETS
    }
    passed = sum(1 for r in rows if not r["why"])
    p95 = statistics.quantiles(seconds, n=20)[-1]
    print(f"model {rows[0]['model']}; version={args.version}; reverse_choice={args.reverse_choice}")
    print(f"jev intent eval: {passed}/{len(rows)} ({passed / len(rows):.0%}); "
          + ", ".join(f"{n} {s}" for n, s in by_set.items())
          + f"; {statistics.fmean(seconds):.2f}s mean, {p95:.2f}s p95 per question; "
          f"{tokens} input tokens ({tokens / len(rows):.0f} per question)")
    print("\n".join(failures))
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
