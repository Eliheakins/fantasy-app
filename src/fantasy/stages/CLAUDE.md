# src/fantasy/stages: refresh pipeline

Each stage is `python -m fantasy.stages.<name>`. `make refresh` runs `fantasy/pipeline.py`, which runs them in the order below. `pipeline.STAGES` is the one list: it marks each stage required (a failure stops the run and records the rest as skipped) or optional (recorded, the run goes on), and network stages as retried twice, 30 s apart. A stage times out after 10 minutes and the run stops starting stages after 20. A new stage goes in `pipeline.STAGES`, not the Makefile. Stages read and write parquet tables registered in `store.SCHEMAS`. A missing table for a layer, calibration or a blend source is skipped without error, and the stale banner lists it (`data_api.missing_layers`).

## Order

0. `backup`: copies `data/archive/` out of the repo, then:
1. `sync_sleeper`, `news_archive` (daily Sleeper status snapshot from the cached players file), `sleeper_projections`, `outside_projections` (outside sources' snapshots), `ingest_nfl`, `crosswalk` (Sleeper to nflverse ID map): raw data.
2. `score` (points per league's scoring), `prop_points` (`proj_props`: this week's prop-implied points from the latest `make odds-slate` snapshot; `proj_outside`: outside sources' latest snapshots, FFToday points), `streaming` (K and DEF projections).
3. `project`: rolling baseline (`proj_baseline`).
   `learn` (package `stages/learn/`; the GBM code it shares is `stages/gbm.py`): gradient-boosted model on lagged stats and role data (`proj_learned`, same schema). `projection_model` in `config.toml` picks which table later stages read, through `store.projection_table()`.
   With `stat_line_model` on (off in the loader, on in `config.toml`), `learn` multiplies by the chance of a stat line from `stages/stat_line.py`, so `proj_learned` is expected points given a played game. Games with no stat row score 0, and past rows are kept for games without a stat line too. The q goes to the `stat_line` table (`src/fantasy/stat_line_table.py`, written after `proj_learned`, deleted when off). The injury layer (`sim/injuries.py`) and the `injuries` stage use it to take q back out where the injury table's chance of playing already counts it.
   `availability`: chance of playing this week (table `availability`).
   `distributions`: size calibration, per-tier marginals and spreads, correlations, fit on the chosen projections.
   `streaming` projects K and DEF with a ridge on trailing form, implied total and kicker features (`streaming_model.py`), blended with Sleeper's, and archives each run in `streaming_snapshots`. DEF points take fumble-return TDs, sack yards, special-teams takeaways and two-point returns from play-by-play (`defense_play_facts`), because nflverse team stats lack them.
4. `injuries`, `outlook`: measured effects (`injury_effects`, `outlook_effects`).
5. `simulate`: applies calibration, the source blend, injury and outlook layers, then season odds. Logic is in `sim/`.
6. `digest`, `market_values`: the digest's stored waiver and trade ideas (`move_ideas`) and FantasyCalc market values, both after `simulate`.
7. `stat-data-refresh` (`python -m nfl_stat.pipeline.cli --refresh`): rebuilds the current season's stat shards from the shared play-by-play cache.

## Run records

- Every step runs through `python -m fantasy.stages.run_recorded <stage> <module>`. `fantasy/_runs.py` (`run_stage`, `record_run`, `latest_runs`, `note_soft_failure`) appends `{stage, finished_at, status, error}` to `refresh_runs` (`data/derived`, never `data/stat`).
- A stage that fails soft calls `note_soft_failure(error)`. It is recorded as failed and later steps still run. Under the pipeline (which sets `FANTASY_SOFT_EXIT`) it exits 65 (`_runs.SOFT_FAILURE_EXIT`), so a network stage is retried like a failure; after the last attempt it counts as ok, even for a required stage. Run alone it exits 0.
- A stage's own recorded error stands: the pipeline adds its "exit code N" row only when the stage recorded nothing (a timeout or a crash before recording). A `SystemExit("message")` records the message.
- The last step, `refresh_report --since <start>`, prints `REFRESH FAILED` for each stage that failed in this run, or when no stage recorded anything since the start, and exits 1. That puts the line in `data/refresh.log` and makes launchd see a failure.
- Each row also has `run_id` (one per `make refresh`, from `FANTASY_RUN_ID`; null for a stage run alone) and `duration_s`. Rows written before 2026-11-09 read as null for both.
- `make refresh` runs inside `python -m fantasy._lock`, which holds `data/.pipeline.lock` for the whole run. The live score tick and the Refresh scores button take the same lock without waiting and skip or answer "busy"; a second `make refresh` waits. The lock is a kernel file lock, so a crash never leaves it stuck. Stages started by the holder skip their own short locks (`FANTASY_PIPELINE_LOCK_HELD`). `pipeline_lock` is not reentrant.
- `/api/status` returns the latest row per stage as `refresh_runs`. The stale banner shows a notice for each failed stage. A stage with no row did not run.

## Releases

- Tables live in a release. `data/current` is a symlink to `data/releases/<id>`, and `store.area_dir` finds raw and derived through it (inside a pipeline run, through `FANTASY_RELEASE_DIR`, the release being built). Before the first migration the tables sit in `data/raw` and `data/derived`, and that still works.
- `pipeline.refresh` builds the next release as a hard-link copy of the current one, runs the stages into it, and flips `current` only if every required stage succeeded. A failed run leaves the old release serving, keeps the failed release folder for inspection, and carries `refresh_runs` over so the banner shows the failure.
- Stages must replace table files (`store.write_table`, `atomic_path`), never overwrite one in place: releases share files through hard links, so an in-place write would change the live release.
- Not in releases: `data/archive`, `data/stat`, and the download caches under `data/raw` (`pbp/`, the Sleeper players file). The first `make refresh` migrates the old layout by itself; `python -m fantasy.releases migrate|prune` does it by hand. The newest 5 releases are kept.

## Gotchas

- `data/archive/` cannot be regenerated. It holds our own weekly projections for the next game (`proj_snapshots`, the clean test of the learned model), Sleeper projection snapshots (re-stamped after games, so only our own are clean), odds snapshots, season-odds history, K and DEF projections (`streaming_snapshots`) and daily Sleeper status snapshots (`sleeper_player_status`, for `research/news_residual_check.py`). `make backup` copies it to `~/fantasy-app-backups` (or `FANTASY_BACKUP_DIR`; keeps 30), and `make refresh` runs it first. Never put the copy in a repository. Issue #40 depends on it.
- Scores enter data on `make refresh`, the Refresh scores button and the live refresh in `make serve` (during games).
- Model features use only games before the target game. Pass a horizon shift to every lagged join (`lag_asof` and `latest_asof` in `stages/lags.py`), and add a test.
- The learned model's past-game projections for 2019 and 2020 come from models that saw later seasons. `store.projection_table()` drops them. Never fit residual sizes or effects on them.
- Held-out error is judged on all played games: offensive snaps or a stat row. A played game with no stat row scores 0 (`learn.hurdle_on_played`).
- `project.future_targets` starts at the league's `current_week` and keeps only games with no score yet. A Thursday game must not hide week N for other teams.
- Run `make refresh` after Sunday, after Monday night, and after Friday's injury report. `learn`'s teammate-vacancy features (`stages/vacancy.py`) use each gameday's final report once published, and only Sleeper's Out players before that.
- The environment layer (opposing-corner and offense-efficiency adjustments) was removed: no held-out gain on the learned projections (`docs/decisions.md`). `nfl_team_efficiency` is no longer built: no K or DEF feature read it (`research/efficiency_freshness_check.py`).
- Held-out checks: `learn` prints the learned model against the size-calibrated baseline. `backtest` adds pinball and coverage by size tier. `research/ros_check.py` and `availability_check.py` are the other checks (`layers_check.py` and `replication.py` import the removed environment stage and no longer run). Run `uv run python -m fantasy.stages.learn`, `availability` and `backtest` after changing a feature.
- Stages that keep the last good data when part fails: `digest` keeps the previous `move_ideas` rows of a league that failed this run; `market_values` treats a response with no usable rows as a soft failure and keeps the stored values; `learn` still archives rows with no baseline (the archive cannot be rebuilt) but flags a soft failure.
- `sleeper_projections` flags a soft failure when a league scores an offense stat key, with a nonzero weight, that no Sleeper projection row carries (a renamed key would otherwise score 0). Defense, points- and yards-allowed buckets and kicker (`fg*`) keys are exempt.
- `sync_sleeper` logs the traceback of a registered league it skips, so a code bug shows in the log and not only as "league failed".
