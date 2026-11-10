"""CLAUDE.md layout rule: `fantasy -> nfl_stat` only, `nfl_stat` never imports `fantasy`."""

import ast
from pathlib import Path

import nfl_stat


def _imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_nfl_stat_never_imports_fantasy() -> None:
    root = Path(nfl_stat.__file__).parent
    offenders = [
        f"{path.relative_to(root)} -> {name}"
        for path in sorted(root.rglob("*.py"))
        for name in _imported_modules(ast.parse(path.read_text()))
        if name == "fantasy" or name.startswith("fantasy.")
    ]
    assert offenders == []
