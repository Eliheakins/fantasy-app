import importlib
import pkgutil

import pytest

from fantasy import stages

MODULES = [m.name for m in pkgutil.iter_modules(stages.__path__)]


@pytest.mark.parametrize("name", MODULES)
def test_every_stage_imports_on_its_own(name: str) -> None:
    importlib.import_module(f"fantasy.stages.{name}")
