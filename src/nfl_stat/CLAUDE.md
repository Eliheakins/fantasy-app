# src/nfl_stat: stat app backend

The stat app's backend, merged in from the old stat app (#70). Fantasy imports this package. It never imports fantasy. Metrics are defined in `metrics/metrics.json` (the source of truth, read by `schemas/metrics.py`). Frontend: `web/src/stat/`.

## Wiring

- `nfl_stat.main.attach(app, settings)` is called by `fantasy.api.create_app` before the SPA mount. It adds `GET /api/stat/health`, `POST /api/stat/nlq/intent` and the static mount `/api/stat/data/*`.
- `/api/stat/health` reports `built_at` of the stat manifest. The banner reads it and marks the data stale after 48 hours (`web/src/lib/status.ts`).
- The fantasy Host and X-Requested-With checks cover these routes. There is no CORS.
- The stat-only `nfl_stat.main.create_app` (used by the stat tests) still returns `{detail}` errors. `web/src/stat/lib/http.ts` reads both error shapes.

## Static mount rule

- Mount only `data/stat` (`AppSettings.data_dir`, env `NFL_STAT_DATA_DIR`). Never mount `data/`, which holds league data. `attach` serves only `settings.data_dir`, never its parent.
- `ShardFiles` serves only `manifest.json`, `players.json` and `*.parquet`, with Range support.
- `data/stat/` holds only nflverse data: never league data and never `nfl_ecr`.

## Shared building blocks

- `core/seasons.py`: `current_season()` is `season` in `config.toml` if set, else nflreadpy's clock. `roster_season()` is the roster variant. Three first-season constants, and they are different things: `FANTASY_FIRST_SEASON` 2018 (fantasy training), `STAT_SHARDS_FIRST_SEASON` 2021 (stat shards), `NFLVERSE_PBP_FIRST_SEASON` 1999 (nflverse play-by-play).
- `core/config.py`: `REPO_ROOT`, `AppSettings` (`data_dir`, the LLM model, the intent provider and Jev settings).
- `pipeline/nflverse.py`: the one fetch of player stats and rosters (`player_stats`, `rosters`, `rosters_weekly`).
- `pipeline/atomic.py`: `atomic_path`. It is used by the shard and manifest writers, `store.write_tables` and the Sleeper players cache, so a file is replaced only once complete.
- `pipeline/cli.py`: `make stat-data` builds every season from `FIRST_SEASON` through the current one. `--refresh` rebuilds only `current_season()`, and other seasons are kept.

## Shared play-by-play

- `pipeline/pbp_source.py` keeps each season's full nflverse play-by-play in `data/raw/pbp/<season>.parquet`. It is raw nflverse data and is never served.
- `ingest_role.load_pace` (fantasy), `environment.team_efficiency` and the stat build all read it, so a season downloads once.
- A file is final, and never refetched, once written on or after March 1 of the next year. Any other file (the season in progress, or a past season fetched mid-season) refetches when older than 12 hours (`TTL_HOURS`). A future mtime counts as stale.
- Downloads must be readable parquet before they replace the cache. Readers pass the columns they need. A season nflverse has not published yet is skipped in `load_pace` only.
- Parity with the old nflreadpy reads was exact (`research/pbp_parity_check.py`; `docs/decisions.md`, 2026-11-04). Delete a file to force a refetch.

## Intent providers (Ask's model step)

- `services/intent_provider.answer_intent` picks the provider. `INTENT_PROVIDER` is `auto` (default: Jev when `JEV_API_KEY` is set, else local), `jev` or `local`. Local is the MLX server from `make ask-model` (port 8080, `llm_model` default equal to the Makefile's `LLM_MODEL`).
- `services/jev_intent.py` is Jev (TypeSafe's hosted model), design 2 of `research/jev_intent_check.py`. Each request carries a Noul per stat and per non-season filter, a Choice for granularity and one for relative seasons. Years are read in code. "This season" uses `current_season()`. Threshold 0.5, at most 5 stats.
- The Jev outcome goes through `nlq_intent.validate_intent`, so every id is in the client's catalog.
- Jev's "leaderboard" Noul sets `QueryIntent.ranking` (it no longer refuses rankings); the client turns a no-player answer with it into a leaderboard. The local model never sets it.
- `services/undefined_terms.py` refuses terms the catalog does not define (over-expected values, routes, pressures, snaps, drops and the like) in code, before Jev or the local model is asked, so neither maps them to a near stat. Remove a term when its stat is defined.
- Any Jev failure (no key, timeout, network or TLS error, 4xx/5xx, malformed answers; `JevError`) falls back to the local server. If that is down too, its 503 reaches the client, whose rules-first path answers what it can.
- One fresh connection per Jev request (reused async TLS connections failed with "bad record mac"). One retry on a transport error, 429 or 5xx. A 429 asking to wait more than 2 s gives up at once. `JEV_TIMEOUT_SECONDS` (10) bounds the whole call.
- Privacy: only the question text and the generic catalog go to Jev (`build_jev_request`; `tests/stat/test_jev_intent.py::test_a_request_built_from_a_question_carries_no_league_data`). Never send league names, ids or rosters. Never log the key, which is a `SecretStr`.

## Eval

- `uv run pytest -m eval` runs against the live model. Eval tests are deselected by default. They need `JEV_API_KEY` or `make ask-model`.
- Jev, no fallback: `set -a; source .env; set +a; uv run pytest -m eval -s`. It scores cases, heldout, heldout2 and corrections. `INTENT_PROVIDER=local` scores Qwen instead. Delete `tests/stat/eval/results.jsonl` afterwards.
- Eval fixtures stay in `tests/stat/eval/`. Web and research reference them, so do not move them.
