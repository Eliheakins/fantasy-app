"""
Terms the stat catalog does not define, refused in code before any model is asked.

A model shown a catalog maps an unknown term to its nearest neighbour (WOPR to explosive rate,
RYOE to rush yards) and the answer looks confident. Refusing these words outright is the honest
answer until the stat exists. Only the question text is read.
"""

from __future__ import annotations

import re

_TERMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in (
        (
            r"\b(over|above) expect(ed|ation)\b|\b(ryoe|yacoe|fpoe)\b",
            "Values over expected (RYOE, YAC over expected, FPOE) are not in the stat data yet.",
        ),
        (r"\broutes?\b|\btprr\b|\byprr\b", "Routes run are not in the play-by-play data."),
        (
            r"\bpressures?\b",
            "Pressures are not in the play-by-play data; hit-to-sack rate uses QB hits instead.",
        ),
        (r"\bsnaps?\b", "Snap counts are not in the stat data yet."),
        (
            r"\bbroken tackles?\b|\bbefore contact\b",
            "Broken tackles and yards before contact are not in the play-by-play data.",
        ),
        (r"\bdrop rate\b|\bdropped passes\b", "Drops are not in the play-by-play data."),
        (
            r"\bnet yards per (pass )?attempt\b|\bny/a\b",
            "Net yards per attempt (NY/A) is not defined; ANY/A and Y/A are.",
        ),
        (
            r"\bproject(ed|ion|ions)\b",
            "Projections are on the Lineup and Players pages, not in Ask's stats.",
        ),
    )
)


def undefined_term(question: str) -> str | None:
    """Why the question names a term the catalog does not define, or None."""
    return next((reason for pattern, reason in _TERMS if pattern.search(question)), None)
