"""
Shared helpers for NLQ routes (Telescope + Microscope).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.config import get_settings


def data_dir() -> Path:
    return get_settings().data_dir


_manifest_cache: dict[str, dict[str, Any]] = {}


def load_manifest(filename: str) -> dict[str, Any]:
    """
    Load a JSON manifest from <DATA_LOCAL_DIR or backend/data>/manifests/<filename>.
    Cached for process lifetime.
    """
    if filename in _manifest_cache:
        return _manifest_cache[filename]
    p = data_dir() / "manifests" / filename
    if not p.is_file():
        raise FileNotFoundError(str(p))
    _manifest_cache[filename] = json.loads(p.read_text(encoding="utf-8"))
    return _manifest_cache[filename]


def normalize_and_validate_select(raw: str, *, required_relation: str) -> str:
    """
    Strip fences, enforce a single safe SELECT statement that references required_relation.
    """
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:sql)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    s = s.strip()

    parts = [p.strip() for p in s.split(";") if p.strip()]
    if len(parts) != 1:
        raise ValueError("Expected exactly one SQL statement")

    stmt = parts[0]
    low = stmt.lower()
    if not low.startswith("select"):
        raise ValueError("Only SELECT statements are allowed")

    low_pad = f" {low} "
    for bad in (
        " insert ",
        " delete ",
        " update ",
        " attach ",
        " copy ",
        " pragma ",
        " drop ",
        " create ",
        " alter ",
    ):
        if bad in low_pad:
            raise ValueError(f"Forbidden keyword: {bad.strip()}")

    compact = low.replace("`", "").replace('"', "").replace("'", "")
    if required_relation.lower() not in compact.lower():
        raise ValueError(f"Query must reference {required_relation}")

    return stmt.rstrip(";") + ";"
