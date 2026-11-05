"""The API read path must not import the batch stages (they pull in training and fetch code).

Unavoidable, imported only inside the function that needs it: `_live.refresh_live` imports
`stages.sync_sleeper` and `live_refresh.LiveRefresher._tick` imports `stages.simulate` and
`stages.sync_sleeper`, because the Refresh scores button and the live tick run those stages.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "fantasy"

CHECK = """
import importlib, sys
sys.path.insert(0, {src!r})
importlib.import_module({module!r})
loaded = sorted(m for m in sys.modules if m.startswith("fantasy.stages"))
print(",".join(loaded))
"""


@pytest.mark.parametrize("module", ["fantasy.api", "fantasy.data_api", "fantasy._engine"])
def test_importing_the_api_loads_no_stage_module(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-c", CHECK.format(module=module, src=str(SRC.parent))],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""


READ_PATH = [
    *sorted(SRC.glob("_*.py")),
    *sorted(SRC.glob("api*.py")),
    SRC / "data_api.py",
    SRC / "live_refresh.py",
    *sorted((SRC / "sim").glob("*.py")),
]
ALLOWED = {"_live.py": "fantasy.stages.sync_sleeper", "live_refresh.py": "fantasy.stages"}


def _stage_imports(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
            found += [f"{node.module}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names]
    return [m for m in found if m == "fantasy.stages" or m.startswith("fantasy.stages.")]


def _is_allowed(path: Path, module: str) -> bool:
    allowed = ALLOWED.get(path.name)
    return allowed is not None and (module == allowed or module.startswith(f"{allowed}."))


def test_no_read_path_module_imports_a_stage_even_lazily() -> None:
    offenders = [
        f"{p.name}: {m}" for p in READ_PATH for m in _stage_imports(p) if not _is_allowed(p, m)
    ]
    assert offenders == []
