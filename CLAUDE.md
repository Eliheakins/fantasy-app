# fantasy-app

Personal NFL fantasy decision tool (Sleeper, redraft, two leagues). Runs on an OVHcloud VPS behind HTTPS and its own sign-in (a Mac works too), Python 3.12 with uv.

Each area has its own CLAUDE.md next to the code, and Claude Code loads it when you work in that folder. Read the one for the area you touch.

## Commands

- `make setup`: install dependencies and enable the git hook. A fresh clone has no data: run `make refresh` next (needs the network).
- `make check`: ruff, mypy (strict on `src`, `src` and `tests` both checked), actionlint, pytest, plus the web typecheck, ESLint, Prettier check, knip and tests. Run before committing. The pre-commit hook runs only ruff and the Prettier check. Never pipe it into `tail`: the pipe hides a failing exit code.
- `make fmt`: auto-fix lint and formatting (ruff and Prettier).
- `make audit`: known advisories in the locked Python and npm dependencies (network). CI runs it before every deploy, and a high or critical npm advisory, or any pip-audit finding, blocks the deploy.
- `make refresh`: back up `data/archive/`, pull Sleeper and nflverse, rebuild every table, and end with `stat-data-refresh`. See `src/fantasy/stages/CLAUDE.md`.
- `make stat-data`: build the stat shards into `data/stat` for every season (network, minutes). `make stat-data-refresh` rebuilds only the current season. See `src/nfl_stat/CLAUDE.md`.
- `make serve`: build `web/` and serve the UI and API at http://127.0.0.1:8000. `make dev`: API plus the Vite dev server (hot reload).
- `make ask-model`: local MLX model server for Ask on port 8080.
- `make odds`: archive one week of prop lines. Needs `ODDS_API_KEY` in the environment or `.env` (gitignored).
- `make schedule-install` / `make schedule-remove`: a macOS launchd job running `make refresh` on Tuesday 06:00, Friday 18:00 and Sunday 08:00. The Mac must be awake; the log is `data/refresh.log`. Installed on the main Mac on 2026-10-28.
- Server (OVHcloud VPS, `ops/server/`): `ops/server/provision.sh admin@host site-hostname` once; `ops/server/push.sh [--data] fantasy@host` to deploy (`--data` only on the first deploy). The server runs the app and `make refresh` from systemd timers; the app is public on the internet behind Caddy HTTPS and its own accounts (`src/fantasy/auth/`).
- Accounts (server): `uv run python -m fantasy.auth create-admin you@example.com` once, then `invite friend@example.com` prints a one-time link; the admin page at `/admin` does the same from the browser. `FANTASY_AUTH=required` (set by `bootstrap.sh`) locks the API until the admin exists; `off` disables login. People add their own Sleeper leagues at `/my-leagues` (2 each).
- Checks against real data: `uv run python -m fantasy.stages.validate_scoring`, `validate_standings`, `backtest`, `calibration`.

## Layout

- Two packages with a one-way dependency, `fantasy -> nfl_stat`. `nfl_stat` never imports `fantasy`.
  - `src/nfl_stat/`: the stat app backend (nflverse build, Ask intent endpoint, shard serving) and the code both halves share.
  - `src/fantasy/`: the fantasy app: refresh stages, pure logic in `sim/`, the API (`api*.py`) and the read facade `data_api.py`.
- Frontend, `web/src/`: layers `stat/` -> `features/` -> `pages/`. `lib/` and `components/` are shared and import neither features nor pages. Routes are in `routes.tsx`, nav in `nav.ts`.
- Tests: `tests/fantasy/{api,engine,stages}/` and `tests/stat/`. Web tests sit beside the code.
- Docs: `docs/one-pager.md` (plan), `docs/backlog.md` (canonical story IDs), `docs/decisions.md` (decisions log), `docs/spec/` (feature specs).
- `research/README.md` indexes every research script by topic and status.

## Conventions

- Parquet under `data/` (gitignored) is the source of truth. Readers use polars. DuckDB is a dev dependency only.
- Lean MVP: simplest method that works, tests only for math and config. CI runs `make check` before every deploy (`.github/workflows/`).
- Annotate function signatures. Prefer frozen dataclasses.
- Log every decision in `docs/decisions.md` as it is made.
- No secrets in the repo. API keys come from environment variables (or the gitignored `.env`).
- Sleeper's API is read-only. Stay under 1,000 calls a minute, and fetch the players file at most once a day.

## Data rules (everywhere)

- `nfl_ecr` (FantasyPros weekly rankings) is private use only. Keep it under the gitignored `data/`. Never commit or share it, and keep it out of shards, fixtures and `web/openapi.json`.
- No paid data (user decision, 2026-10-23). A free source may be scraped and stored unless its terms forbid it (user decision, 2026-10-26; sources in `research/notes/2026-10-26-research-survey.md`). Third-party data is never committed.
- ESPN (YinzBurgh 2023 to 2025, private; Colgate has no earlier seasons): `ESPN_S2` and `ESPN_SWID` live in `.env`, never in a command or in chat. Research only, see `research/CLAUDE.md`.
- League data never goes under `data/stat`, because that folder is served over HTTP, and never reaches a model prompt. Ask sends a model only the question text and the generic catalog.
- `data/archive/` cannot be regenerated. See `src/fantasy/stages/CLAUDE.md`.

## Model standard

A change to a projection or distribution ships only if it improves held-out error (fit 2019 to 2023, score 2024 on) or has a clear t-statistic (|t| of 2 or more), and the stages and tests pass. Held-out error is judged on all played games, with the `compare_to_baseline` rows reported alongside (user decision, 2026-10-26). Record every test, shipped or not, with numbers in `docs/decisions.md`. Method and rejected ideas: `research/CLAUDE.md`.

## Dates that matter (2026 season)

- Trade deadline: week 11. Issue #40 (retest the 50% Sleeper blend weight on clean snapshots) is due around then.
- `make odds` costs about 80 of 500 monthly credits per snapshot.

## Area files

- `src/fantasy/CLAUDE.md`: API, read facade and private modules, request context, live refresh.
- `src/fantasy/stages/CLAUDE.md`: refresh pipeline, run records, backups, model gotchas.
- `src/fantasy/sim/CLAUDE.md`: simulation, league data, point-effect scaling.
- `src/nfl_stat/CLAUDE.md`: stat backend, shard serving, shared play-by-play, intent providers, eval.
- `web/CLAUDE.md`: UI conventions, nav, fetch family, generated types.
- `web/src/stat/CLAUDE.md`: query engine, stat/react kernel, league points.
- `web/src/features/explore/CLAUDE.md`: Find players and the league filter.
- `web/src/features/players/CLAUDE.md`: Player page and compare.
- `web/src/features/ask/CLAUDE.md`: Ask, rules, start/sit, trades, ask log.
- `research/CLAUDE.md`: how a research test is run, ESPN fetch, rejected ideas.
- `tests/CLAUDE.md`: test layout, fixtures, eval marker.
