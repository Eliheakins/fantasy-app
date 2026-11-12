# src/fantasy: API and read layer

The FastAPI app (`api.py`, the route package `api_routes/` with one module per area, and the response models in `api_models/`) and the read layer behind it. Refresh stages: `stages/CLAUDE.md`. Simulation: `sim/CLAUDE.md`.

## Read path

- `api_routes/` imports `data_api`, `_live`, `_view`, `api_deps` and `api_envelope`.
- The read path imports no `fantasy.stages` module. The exceptions import inside a function: `_live.refresh_live` (Sleeper sync) and `live_refresh` (simulate and sync). Test: `tests/fantasy/api/test_api_import_boundary.py`.
- `data_api.py` is a read facade. It re-exports entry points from the private `_` modules, so callers use `data_api.<name>`. Put new read logic in the `_` module that owns it, and re-export it from `data_api`.
- `_` modules:
  - `_engine.py`: `_league(league_key, data_dir, team)` returns the simulation inputs and "my" roster id, built once per data version. `_league_id` is one filtered read for display reads that need no projections or draws. `_week_values` gives current-week lineup values.
  - `_leagues.py`: `leagues`, `scoring_labels`, `my_league`, `team_fields`.
  - `_next_game.py` (a team's next unplayed game or bye, and its bye week), `_lineup.py`, `_outlook.py` (`player_owners`, `schedule`, `player_outlook`), `_market.py` (`player_points`, market reads), `_profile.py` (`player_profile`).
  - `_status.py` (`freshness`, `simulation_behind_inputs`, `missing_layers`, `refresh_runs`), `_calendar.py` (`week_calendar`, `status_changes`), `_actions.py` (`actions`, `streamers`).
  - `_live.py` (`refresh_live`, `live_win_row`, `record_live_tick`, `game_day`) is the live writer.
  - `_scoreboard.py`, `_scorecard.py`, `_values.py`, `_watch.py`, `_season_events.py`, `_league_view.py`, `_digest.py`, `_schemas.py`, `_view.py` (page logic the API serves).

## Request context

- `api_deps.py`: `RequestContext(data_dir, team, job_owner)`. `job_owner` is a non-admin account's id, which caps that account at `MAX_ACTIVE_PER_OWNER` (4) running jobs; it is None for the admin and with login off. `create_app(data_dir=None)` sets `app.state.data_dir` once.
- A route takes `Ctx` (data dir plus the `?team=` roster id) or `DataDir` (no team), and passes the values down as arguments. Nothing is read from a global. `_engine.viewing_team` is gone.
- `?team=<roster id>` on any `/api/leagues/{league}/...` route makes that team "me".
- Anything that decides "my team" goes through `_league()` or `_leagues.my_league`. Never read `league_teams.is_me` directly. Sleeper's `is_me` flag decides, not the top team. My teams: Colgate "Lisan Al-Caleb", YinzBurgh "LaPorta Potty".

## API rules

- Non-GET requests need `X-Requested-With: fantasy-app`. The server binds 127.0.0.1 and rejects unknown Host headers; extra names go in `API_ALLOWED_HOSTS`, comma separated. Outside access only through the server's Caddy (HTTPS, `ops/server/`), which proxies to the localhost bind. Login is the app's own (`auth/`, below); never expose port 8000 directly. Put the site hostname in `API_ALLOWED_HOSTS`.
- Errors use one envelope. `guarded()` answers HTTP 200 for no data (`no_data`) and a rejected request (`invalid`), and 500 for an unexpected exception (`server`, logged). Other errors use the same shape with real status codes (`register_error_handlers` in `api_envelope.py`). The web client reads the envelope whatever the status.
- OpenAPI: `uv run python -m fantasy.api --openapi > web/openapi.json`, then `cd web && npm run types`. Checks are in `web/CLAUDE.md`.
- The stat routes (`/api/stat/*`) are attached by `create_app`. See `src/nfl_stat/CLAUDE.md`.
- `/api/status` sends stage error text only to the admin (and with login off); a friend gets each stage's status with `error` null.
- The served app runs with uvicorn's access log off, so the `/invite/<token>` page load never reaches the journal.

## Live refresh

- `make serve` runs `live_refresh.py` every 5 minutes while a game of the current week is on: `sync_week`, then `simulate.run(archive=False)`. `LIVE_REFRESH=off` disables it.
- Never let a live tick append to `sim_season_history`.
- A live tick, and the Refresh scores button, append one row per league for my team to `live_win_history` (current week only, deduplicated by `run_at`, written by `data_api.record_live_tick`). The game-day block on This week reads it.

## Gotchas

- Current-week lineup values include players whose game is over, at their actual points (`_engine._week_values`). Never read `moves.week_values` for a current-week lineup.
- Known gaps, not fixed: `PLAYERS_CACHE` (`stages/sync_sleeper.py`) and `ODDS_DIR` (`stages/snapshot_odds.py`) are import-time paths that ignore `data_dir`.

## Accounts and login (`auth/`)

- `data/auth.db` (SQLite; backed up with the archive by `stages/backup.py`) holds accounts, invites, sessions, `account_leagues` and `league_registry`. Passwords are scrypt (`passwords.py`, at most 2 hashes at once); invite and session tokens are stored only as SHA-256 hashes. `accounts.connect` makes the db and its WAL files mode 600. Sign out ends the current session; `POST /api/auth/logout-everywhere` ends every session of that account (the Footer's "Sign out everywhere").
- The gate (`routes.install`, a middleware) runs for every `/api/*` request except login and redeem. It is on once an account exists; `FANTASY_AUTH=required` turns it on before that, `off` disables it. `policy.decide` is the whole rule: a signed-in member reads everything they may see and uses the compute-only POSTs plus add/remove of their own leagues; every other write, and `/api/admin/*`, is the admin's. A new write route is admin-only until it is listed in `policy.FRIEND_WRITES`; `test_auth_policy.py` pins the full list of write routes.
- League access (`access.py`): a league is visible to the account that added it; the admin also sees the leagues in `config.toml`. Nobody sees another account's league. The middleware answers 404 for any other `/api/leagues/{league}/...`; `/api/leagues` and `/api/week-calendar` are filtered. With no `?team=`, `get_context` views the account's team: the roster it picked (`account_leagues.roster_id`), else the roster its Sleeper user owns, in every league including the owner's (`access.account_rosters`). Only a league where the account has neither falls back to Sleeper's `is_me` (the admin's `config.toml` leagues).
- Added leagues (`my_leagues.py`, `leagues.py`): lookup by Sleeper username (rate limited), the league's teams to pick from (`GET /api/me/sleeper/leagues/{id}/teams`, same limit), add (needs the picked `roster_id`, a team owned by that user, the league must be a current-season league of theirs, an account stays linked to the first Sleeper user it used, 2 leagues per account), change team (`PUT /api/me/leagues/{id}/team`), remove. A new account with no leagues gets a first-visit dialog (`web/src/features/leagues/WelcomeDialog.tsx`). `sync_sleeper` reads them next to `config.toml`; a failing one is marked `error` in the registry and skipped, while a failing config league still stops the run. `sim.season.format_problem` refuses leagues the 6-team-playoff model cannot fit, at add time and again in `simulate`. Add time also refuses scoring keys `scoring.check_keys` cannot map (`UnmappedScoring`) and lineup slots `sim/lineup.py` does not know (`UnknownSlot`); `score` and `simulate` skip an added league that raises either (logged, `note_soft_failure`, registry marked `error` through `auth/leagues.skip_added`), while a `config.toml` league that does still stops the run. Non-admin accounts cannot add a `config.toml` league or use the owner's Sleeper user.
- A league someone else added has no `is_me` team: `_engine._league` needs a named team for it, the `digest` stage skips it, and `reference_league` ignores it (the effects stay measured in the owner's leagues).
- Ask's model: on the server `JEV_API_KEY` lives in `~/fantasy-app/.env` (mode 600, never in the repo; the deploy leaves `.env` alone). There is no local model there (MLX needs Apple Silicon), so without the key only rule-readable questions work. Every call to `/api/stat/nlq/intent` is a paid model call, so the gate allows each account `INTENT_PER_MINUTE` (20) a minute and answers 429 after that (`auth/routes.py`).
