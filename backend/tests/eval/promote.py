"""
Adds the corrections exported from the History page (ask-corrections.json) to `corrections.json`,
the eval set made of questions a user had to fix:
    uv run python backend/tests/eval/promote.py ~/Downloads/ask-corrections.json

Both evals score the set: the model eval reports it, the rules eval fails on any wrong answer.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nfl_stat.schemas.nlq import Granularity

EVAL_DIR = Path(__file__).parent
SETS = ("cases", "heldout", "corrections")


class PromoteError(ValueError):
    pass


class _Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=1, max_length=2000)
    stats: list[str] = Field(min_length=1)
    filters: list[str]
    granularity: Granularity


def _key(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip().casefold()


def _validate(raw: Any, stat_ids: set[str], filter_ids: set[str]) -> dict[str, Any]:
    try:
        parsed = _Case.model_validate(raw)
    except ValidationError as e:
        fields = ", ".join(str(err["loc"][0]) for err in e.errors() if err["loc"])
        raise PromoteError(f"{raw!r}: invalid {fields or 'case'}") from e
    unknown = [f"stat {s!r}" for s in parsed.stats if s not in stat_ids] + [
        f"filter {f!r}" for f in parsed.filters if f not in filter_ids
    ]
    if unknown:
        raise PromoteError(f"{parsed.q!r}: unknown {', unknown '.join(unknown)}")
    return parsed.model_dump()


def promote(
    exported: Any, existing: dict[str, list[dict[str, Any]]], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    """The exported cases to add: valid against the catalog and not already in any set."""
    if not isinstance(exported, list):
        raise PromoteError("the export must be a list of cases")
    stat_ids = {s["id"] for s in catalog["stats"]}
    filter_ids = {f["id"] for f in catalog["filters"]}
    seen = {_key(c["q"]) for cases in existing.values() for c in cases}
    added: list[dict[str, Any]] = []
    for raw in exported:
        valid = _validate(raw, stat_ids, filter_ids)
        if _key(valid["q"]) not in seen:
            seen.add(_key(valid["q"]))
            added.append(valid)
    return added


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise PromoteError(f"cannot read {path}: {e}") from e


def main(argv: list[str], eval_dir: Path = EVAL_DIR) -> int:
    if len(argv) != 1:
        print("usage: promote.py <ask-corrections.json>", file=sys.stderr)
        return 2
    try:
        existing = {name: _read(eval_dir / f"{name}.json") for name in SETS}
        added = promote(_read(Path(argv[0])), existing, _read(eval_dir / "catalog.json"))
    except PromoteError as e:
        print(f"promote: {e}", file=sys.stderr)
        return 1
    corrections = [*existing["corrections"], *added]
    lines = ",\n".join(f"  {json.dumps(c)}" for c in corrections)
    (eval_dir / "corrections.json").write_text(f"[\n{lines}\n]\n" if corrections else "[]\n")
    print(f"added {len(added)} correction(s); corrections.json now has {len(corrections)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
