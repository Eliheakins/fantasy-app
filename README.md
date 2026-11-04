# NFL Stat App — The Bridge

A local NFL stats workbench. Ask a question like "Mahomes passing yards and touchdowns in 2023" and get an answer and a table.

- **Backend:** FastAPI asks a local model to turn a question into stats and filters, and (locally) serves the static data files: the manifest, the player list and the play-by-play Parquet shards.
- **Frontend:** Vite + React. A small columnar engine (`frontend/src/shared/engine/`, hyparquet plus an evaluator for the SQL expressions in `metrics/metrics.json`) runs the queries in the browser, reading only the Parquet columns a query needs over HTTP range requests. A local model never writes queries and never sees player ids.

Everything runs on your machine. Data lives in `backend/data/`.

## How Ask works

1. Player names in the question are matched in the browser against the static player list (`players.json`). Namesakes are narrowed by the stats asked about, or you pick one.
2. `POST /nlq/intent` sends the question and the stat/filter catalog to a local model, which returns `{outcome: "query", intent: {stat_ids, filter_ids, granularity}}`, or `{outcome: "unsupported", reason}` when no stat can answer (salary, fantasy points, opinions). The reply is validated, with one retry on a bad reply.
3. The Explore query builder hands the stats and filters to the in-browser engine. The answer text is built from the result rows, not by the model.
4. Questions default to the regular season unless they mention the playoffs.

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js 20+, and an Apple Silicon Mac for the MLX model server.

```bash
uv sync                       # backend dependencies (add --group llm for the model server)
cd frontend && npm install
```

### Data

```bash
uv run python backend/scripts/build_data.py            # 2021 through the current season
uv run python backend/scripts/build_data.py --years 2023,2024
```

This writes, into `backend/data/`:

| File | What it is |
|------|------------|
| `nfl_pbp_YYYY.parquet` | Play-by-play, one file per season, with participation and Next Gen Stats joined on |
| `player_game.parquet` | One row per player per game with official counting totals (tier 1, not used by Ask yet) |
| `player_index.parquet` | One row per player; the build turns it into `players.json` |
| `players.json` | Player list the browser searches and matches names against (id, name, team, position) |
| `manifest.json` | What was built: seasons, files, rows, latest week, and when |

The season list comes from the data: a new season appears in the app as soon as its shard is built, with no code change. Missing values (Next Gen Stats cover only some plays, participation is not published until after a season ends) stay null, and the build prints how much of each column is missing. Re-run the build weekly to pick up new games. If a brand-new season has no play-by-play published yet, build with `--years` up to the previous season.

`/health` reports `data_through` (for example `2026 week 8`) and the seasons loaded. The data files are static: the API's only dynamic endpoint is `POST /nlq/intent`. The browser reads `manifest.json`, `players.json` and the Parquet shards from one base URL, so they can be served from a CDN instead (see `VITE_DATA_BASE_URL` below).

## Run

Three terminals, from the repository root:

```bash
# 1. Local model (first run downloads about 8 GB)
uv run --group llm mlx_lm.server --model mlx-community/Qwen2.5-14B-Instruct-4bit --port 8080

# 2. API
cd backend && uv run uvicorn main:app --port 8100

# 3. Frontend
cd frontend && npm run dev
```

Open `http://localhost:3000`. The API is `http://localhost:8100` (docs at `/docs`, health at `/health`). The API uses 8100 so it does not clash with other local servers on 8000.

The API pings the model every 20 seconds to keep its weights in memory. Without that, the first question after a pause took 20 to 40 seconds while macOS paged the model back in.

## Configuration

Optional, in the environment or a `.env` file at the repository root.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | OpenAI-compatible server (any local server works, for example LM Studio) |
| `LLM_MODEL` | `mlx-community/Qwen2.5-14B-Instruct-4bit` | Must match the model the server loaded |
| `LLM_TIMEOUT_SECONDS` | `120` | Per-request timeout |
| `VITE_API_BASE_URL` | `http://localhost:8100` | Where the browser finds `POST /nlq/intent` (frontend, set when starting Vite) |
| `VITE_DATA_BASE_URL` | `<VITE_API_BASE_URL>/data` | Where the browser finds `manifest.json`, `players.json` and the shards. Point it at a CDN and nothing else changes; the host must allow CORS for the page's origin and answer HTTP Range requests (expose `Content-Range`, `Content-Length` and `Accept-Ranges`). The API's own CORS list is only the local Vite origins |
| `PIPELINE_GC` | `1` | Set `0` to skip `gc.collect()` between seasons in the data build |
| `NFLVERSE_DOWNLOAD_BASE` | nflverse GitHub releases | Override the PBP download host |

## Tests

```bash
uv run pytest --cov=backend           # backend unit and API tests
uv run pytest -m eval -s              # intent accuracy against the live local model (needs step 1 above)
cd frontend && npm test               # name matching, answer text, catalog sync
cd frontend && npm run export:catalog # refresh backend/tests/eval/catalog.json after changing stats or filters
uv run ruff check backend
```

`backend/tests/eval/cases.json` holds 40 questions with expected stats, filters and granularity. The last run passed 39 of 40.

## Layout

| Path | Role |
|------|------|
| `backend/main.py` | App factory: routers, CORS for the local Vite port, static `/data` |
| `backend/api/routers/` | `health`, `nlq` (intent). Everything else is static files under `/data` |
| `backend/services/` | `nlq_intent` (prompt, validation, retry), `llm_client`, `llm_warmup`, catalogs |
| `backend/pipeline/` | Data build from nflverse: play-by-play shards, the player-game table, the manifest (`build_data.py` is the entry point) |
| `frontend/src/features/nlq/` | Ask: name matching, hook, answer text, panel |
| `frontend/src/features/explore/` | Query builder and results canvas (also runs Ask's query) |
| `metrics/metrics.json` | The stat definitions: SQL, aliases, row filters and reference values. Read by the app and by the backend tests |
| `frontend/src/shared/config/` | Loads `metrics.json`; filter chips. The source for the model's catalog |

## Known limits

- Play-by-play has one or two fewer pass attempts than the official tables in some games (Mahomes 2023: one play in week 5 and one in week 11), so rates match the official figures to within about 0.5%, not exactly. Passing yards, touchdowns, receptions and rushing totals for the sampled player-seasons match exactly. Each metric's `reference_values` in `metrics/metrics.json` record the tolerance.
- Sack, penalty and no-play rows are pass plays in the data. Attempt-based stats (passing yards, passing TDs, completion %, interception rate) leave them out with a `play_filter`; edit that in `metrics/metrics.json` and run `uv run pytest`, which checks every metric against its reference values when data is built.
- Per game divides by the games a player appeared in within the same season, season type, week and home/away filters. Situational filters (down, quarter, ...) do not shrink that count.
- The expression language in `metrics/metrics.json` and the filter chips is a SQL subset: `SUM/AVG/COUNT/NULLIF`, `CASE`, `CAST(.. AS DOUBLE)`, arithmetic, comparisons, `AND/OR/NOT`, `LIKE`. `frontend/src/shared/engine/expression.ts` names anything else it cannot run. There is no ad hoc SQL.
- "Min plays" counts the rows each stat uses: attempts for the filtered stats above, dropbacks (sacks included) for the rest. A passer near the threshold can show some stats and not others.
- Per-play values for EPA and WPA stats are per dropback; per-play passing yards, TDs, completion % and interception rate are per attempt.
- No league-wide leaderboards ("who led the league in..."); Ask needs a named player.
- Name matching is exact on surnames and full names, so typos are not corrected.
- Receiving and rushing totals can differ slightly from official lines (play-by-play data).
- `mlx_lm.server` is not hardened for production; keep it on localhost.
