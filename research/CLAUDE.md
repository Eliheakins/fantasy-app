# research: one-off analysis scripts

The scripts behind the entries in `docs/decisions.md`. Plans and surveys are in `research/notes/`. They are not maintained code. Ruff skips this folder, and no test imports them, except `tests/fantasy/engine/test_public_features.py`, which loads `public_features.py` by path. Older scripts were copied here from a scratch folder, so expect to fix a path or column name before a rerun.

## Running

- Run from the repo root, after `make refresh`: `uv run python research/<script>.py`. Each script prints its result. The decisions log has the numbers that were acted on.
- The scripts sit in one folder on purpose. Several import a sibling (`wf_panel`, `bias_check`, `pbp_features_check`, `fd_panel`, `data_value`), which works because Python puts the script's folder on the path.
- Caches go to `research/scratch/` (gitignored). Third-party data (prop archives, outside projections, FantasyPros) stays there and is never committed.

## How a test is run (since 2026-10-25)

- Walk-forward by season: each season is scored by models trained on earlier ones. Scored on 2024, 2025 and 2026, on the `learn.compare_to_baseline` rows unless a script says otherwise.
- RMSE with a paired per-week t. The two leagues share player-games, so they are one test.
- The ship rule is written down before the run. Gains under about 0.1% are inside refit noise for anything not deterministic (see the 2026-10-25 entry).
- The model standard is in the root `CLAUDE.md`.

## Rejected ideas

- `research/README.md` indexes every script by topic, with its result and status in tables. Read the rejected rows before proposing an idea again.

## ESPN

- YinzBurgh's ESPN league id is 1470881390 (private). It is an ESPN id, not the Sleeper id in `config.toml`.
- `espn_fetch.py` needs `ESPN_S2` and `ESPN_SWID` in `.env`. Never put them in a command or in chat. It saves raw JSON under `research/scratch/espn/`.
- `espn_parse.py` makes lineup tables there. Fetched and parsed on 2026-10-28. Only research checks read it; nothing in the pipeline does.
