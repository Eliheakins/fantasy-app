#!/usr/bin/env python3
"""CLI entry: delegates to ``pipeline.cli`` (backend dir on ``sys.path``)."""

from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from pipeline.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
