from __future__ import annotations

import pytest
from compare_models import parse_footprint

FOOTPRINT_OUTPUT = """======================================================================
mlx_lm.server [4321]: 64-bit    Footprint: {value} (16384 bytes per page)
======================================================================
"""


@pytest.mark.parametrize(
    ("value", "megabytes"),
    [("2304 KB", 2.25), ("812 MB", 812.0), ("8.5 GB", 8704.0)],
)
def test_parse_footprint_reads_the_total_in_megabytes(value: str, megabytes: float):
    assert parse_footprint(FOOTPRINT_OUTPUT.format(value=value)) == megabytes


def test_parse_footprint_fails_loudly_on_unexpected_output():
    with pytest.raises(ValueError, match="footprint"):
        parse_footprint("footprint: no process found")
