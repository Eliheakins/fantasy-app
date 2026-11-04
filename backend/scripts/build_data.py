#!/usr/bin/env python3
"""CLI entry: delegates to ``nfl_stat.pipeline.cli``."""

from __future__ import annotations

from nfl_stat.pipeline.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
