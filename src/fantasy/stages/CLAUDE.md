# src/fantasy/stages: refresh pipeline

Each stage is `python -m fantasy.stages.<name>`. `make refresh` runs them in the order below. Stages read and write parquet tables registered in `store.SCHEMAS`. A missing table for a layer, calibration or a blend source is skipped without error, and the stale banner lists it (`data_api.missing_layers`).

## Order

0. `backup`: copies `data/archive/` out of the repo, then:
1. `sync_sleeper`, `news_archive` (daily Sleeper status snapshot from the cached players file), `sleeper_projections`, `outside_projections` (outside sources' snapshots), `ingest_nfl`, `crosswalk` (Sleeper to nflverse ID map): raw data.
2. `score` (points per league's scoring), `prop_points` (`proj_props`: this week's prop-implied points from the latest `make odds-slate` snapshot; `proj_outside`: outside sources' latest snapshots, FFToday points), `streaming` (K and DEF projections).
3. `project`: rolling baseline (`proj_baseline`).
   `learn`: gradient-boosted model on lagged stats and role data (`proj_learned`, same schema). `projection_model` in `config.toml` picks which table later stages read, through `store.projection_table()`.
   With `stat_line_model` on (off in the loader, on in `config.toml`), `learn` multiplies by the chance of a stat line from `stages/stat_line.py`, so `proj_learned` is expected points given a played game. Games with no stat row score 0, and past rows are kept for games without a stat line too. The q goes to the `stat_line` table (`src/fantasy/stat_line_table.py`, written after `proj_learned`, deleted when off). The injury layer (`sim/injuries.py`) and the `injuries` stage use it to take q back out where the injury table's chance of playing already counts it.
   `availability`: chance of playing this week (table `availability`).
   `distributions`: size calibration, per-tier marginals and spreads, correlations, fit on the chosen projections.
   `streaming` projects K and DEF with a ridge on trailing form, implied total and kicker features (`streaming_model.py`), blended with Sleeper's, and archives each run in `streaming_snapshots`.
4. `injuries`, `outlook`, `environment`: measured effects (`injury_effects`, `outlook_effects`, `environment_effects`).
5. `simulate`: applies calibration, the source blend, injury, outlook and (if `environment_layer` is on) environment layers, then season odds. Logic is in `sim/`.
6. `digest`, `market_values`: the digest's stored waiver and trade ideas (`move_ideas`) and FantasyCalc market values, both after `simulate`.
7. `stat-data-refresh` (`python -m nfl_stat.pipeline.cli --refresh`): rebuilds the current season's stat shards from the shared play-by-play cache.

## Run records

- Every step runs through `python -m fantasy.stages.run_recorded <stage> <module>`. `fantasy/_runs.py` (`run_stage`, `record_run`, `latest_runs`, `note_soft_failure`) appends `{stage, finished_at, status, error}` to `refresh_runs` (`data/derived`, never `data/stat`).
- A stage that fails soft calls `note_soft_failure(error)`. It is recorded as failed and exits 0, so later steps still run.
- The last step, `refresh_report --since <start>`, prints `REFRESH FAILED` for each stage that failed in this run and exits 1. That puts the line in `data/refresh.log` and makes launchd see a failure.
- `/api/status` returns the latest row per stage as `refresh_runs`. The stale banner shows a notice for each failed stage. A stage with no row did not run.

## Gotchas

- `data/archive/` cannot be regenerated. It holds our own weekly projections for the next game (`proj_snapshots`, the clean test of the learned model), Sleeper projection snapshots (re-stamped after games, so only our own are clean), odds snapshots, season-odds history, K and DEF projections (`streaming_snapshots`) and daily Sleeper status snapshots (`sleeper_player_status`, for `research/news_residual_check.py`). `make backup` copies it to `~/fantasy-app-backups` (or `FANTASY_BACKUP_DIR`; keeps 30), and `make refresh` runs it first. Never put the copy in a repository. Issue #40 depends on it.
- Scores enter data on `make refresh`, the Refresh scores button and the live refresh in `make serve` (during games).
- Model features use only games before the target game. Pass a horizon shift to every lagged join (`lag_asof` and `latest_asof` in `stages/lags.py`), and add a test.
- The learned model's past-game projections for 2019 and 2020 come from models that saw later seasons. `store.projection_table()` drops them. Never fit residual sizes or effects on them.
- Held-out error is judged on all played games: offensive snaps or a stat row. A played game with no stat row scores 0 (`learn.hurdle_on_played`).
- `project.future_targets` starts at the league's `current_week` and keeps only games with no score yet. A Thursday game must not hide week N for other teams.
- Run `make refresh` after Sunday, after Monday night, and after Friday's injury report. `learn`'s teammate-vacancy features (`stages/vacancy.py`) use each gameday's final report once published, and only Sleeper's Out players before that.
- `environment_layer = false` in `config.toml`: the corner and offense-efficiency adjustments had no held-out gain on the learned projections. The stage and code remain.
- Held-out checks: `learn` prints the learned model against the size-calibrated baseline. `backtest` adds pinball and coverage by size tier. `research/ros_check.py`, `layers_check.py` and `availability_check.py` are the other checks. Run `uv run python -m fantasy.stages.learn`, `availability` and `backtest` after changing a feature.
