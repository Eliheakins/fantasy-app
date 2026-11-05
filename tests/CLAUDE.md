# tests: layout and fixtures

Run with `uv run pytest -q`, or through `make check`, which also runs ruff, mypy and the web checks.

## Layout

- `tests/fantasy/api/`: the API, `data_api` and the `_` read modules. `test_api_import_boundary.py` checks that the read path imports no stage.
- `tests/fantasy/engine/`: the simulation and the pure logic in `sim/`.
- `tests/fantasy/stages/`: the refresh stages.
- `tests/stat/`: the stat backend (`nfl_stat`), including `test_jev_intent.py` and `test_metric_reference_values.py` (which runs `metrics.json` SQL through duckdb, a dev dependency).
- `tests/stat/eval/`: eval fixtures (`cases.json`, `heldout.json`, `heldout2.json`, `corrections.json`) and scripts. Web and research reference these, so do not move them.

## Fixtures and helpers

- `tests/conftest.py`: `store_dir` (a tiny parquet store in a temporary directory), `client` (a TestClient over it) and `league`.
- `tests/store_fixture.py`: helpers that build that store.
- `tests/stat/fakes.py`: `FakeLlm`, `STATS` and `FILTERS`.
- Bare-name imports work because `pyproject.toml` sets `pythonpath` to `tests` and the test subfolders. Basenames must be unique across them.

## Eval marker

- Tests marked `eval` run against the live model. They are deselected by default (`addopts = -m 'not eval'`). Run `uv run pytest -m eval`, which needs `JEV_API_KEY` or `make ask-model`. The scoring commands are in `src/nfl_stat/CLAUDE.md`.

## Web tests

- Vitest, beside the code. Run `npm test` in `web/`.
