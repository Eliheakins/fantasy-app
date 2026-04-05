# NFL Stat App — The Bridge

A local NFL analytics workbench: a **FastAPI** backend serves a **player index** and **play-by-play Parquet shards**, while a **Vite + React** frontend (**The Bridge**) runs **DuckDB-WASM** in the browser to query those Parquets over HTTP.

The same codebase can run **locally** (disk-backed `backend/data/`) or **hosted on [Render](https://render.com/)** (API web service, static frontend, optional persistent disk for Parquet files). You can also serve Parquet from **object storage** (for example **Cloudflare R2**) using `DATA_SOURCE=r2`.

---

## Setup and build

### Prerequisites

- **Python 3.12+** (recommended) with `pip`
- **Node.js 20+** and **npm** (for the frontend)

### 1. Backend (Python)

From the repository root:

```bash
python -m venv venv
```

Activate the virtual environment (Windows PowerShell):

```bash
.\venv\Scripts\Activate.ps1
```

Install runtime dependencies:

```bash
pip install -r backend/requirements.txt
```

For linting, tests, and typing as well:

```bash
pip install -r backend/dev-requirements.txt
```

### 2. Data files (local)

Generate Parquet shards and the player index (writes into `backend/data/`):

```bash
python backend/scripts/dataPipeline.py
```

You should end up with:

- `backend/data/player_index.parquet`
- `backend/data/nfl_pbp_YYYY.parquet` (one file per season in the pipeline)

### 3. Run the API (local)

From the `backend` directory:

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`
- Interactive docs: `http://127.0.0.1:8000/docs`
- Parquet files are exposed under `http://127.0.0.1:8000/data/...` when `DATA_SOURCE=local` (default)

### 4. Frontend (Vite + React)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

- App: `http://localhost:3000` (default Vite port in this project)
- Optional: create `frontend/.env.local` with `VITE_API_BASE=http://127.0.0.1:8000` if your API URL differs

**Production build:**

```bash
cd frontend
npm run build
npm run preview
```

Output is written to `frontend/dist/`. The `frontend/public/_redirects` file is copied into `dist/` for hosts that use it (for example Netlify-style `_redirects`); on **Render**, SPA fallback is configured in `render.yaml`.

---

## Configuration (environment variables)

### Backend (`backend/main.py`)

| Variable | When | Description |
|----------|------|-------------|
| `DATA_LOCAL_DIR` | Optional | Absolute path to the directory containing `player_index.parquet` and `nfl_pbp_*.parquet` for local mode. Default: `backend/data` next to `main.py`. On Render, set to your persistent disk mount (for example `/data`) via `render.yaml`. |
| `CORS_ORIGINS` | Always (optional) | Comma-separated browser origins allowed to call the API. Default: `http://localhost:3000,http://127.0.0.1:3000`. In production, include your static site URL(s), e.g. `https://your-service.onrender.com` |
| `DATA_SOURCE` | Always (optional) | `local` (default) or `r2` |
| `PLAYER_INDEX_PATH` | `DATA_SOURCE=local` | Path to `player_index.parquet`. Default: `<DATA_LOCAL_DIR or backend/data>/player_index.parquet` |
| `PLAYER_INDEX_URL` | `DATA_SOURCE=r2` | **Required.** HTTPS URL to `player_index.parquet` (e.g. public object URL) |
| `PUBLIC_PBP_BASE` | `DATA_SOURCE=r2` | **Required.** HTTPS base URL (no trailing slash) where `nfl_pbp_YYYY.parquet` objects are readable, e.g. `https://<bucket>.<account>.r2.cloudflarestorage.com` or a custom domain |
| `PBP_YEARS` | `DATA_SOURCE=r2` | **Required.** Comma-separated seasons matching files in object storage, e.g. `2021,2022,2023,2024,2025` |

With `DATA_SOURCE=r2`, the API does **not** mount `/data` from disk; shard `path` values in JSON are **absolute HTTPS URLs** so the browser (DuckDB-WASM) fetches Parquet **directly from storage**. Configure **CORS on the bucket** to allow `GET` from your static site origin.

### Frontend (Vite)

| Variable | Build-time | Description |
|----------|------------|-------------|
| `VITE_API_BASE` | Yes | Base URL of the FastAPI service (no trailing slash). Default in code: `http://localhost:8000`. Set when building on **Render** (Blueprint prompts for `sync: false` vars) or in CI |

**No boto3** is required for the current R2 mode: objects are addressed by public HTTPS URLs. If you later use a **private** bucket, you would add server-side presigned URLs (e.g. with `boto3`)—not implemented in this repo yet.

---

## Hosted deployment (Render)

Use the repo root [`render.yaml`](render.yaml) with [Render Blueprints](https://render.com/docs/infrastructure-as-code).

1. **Create a Blueprint** from this repository. Render will provision:
   - **nfl-stat-api** — Python web service (`rootDir: backend`), health check `GET /health`, persistent disk mounted at `/data` with `DATA_LOCAL_DIR=/data`.
   - **nfl-stat-ui** — Static site (`rootDir: frontend`), publish directory `./dist` (Render paths are relative to `rootDir`, so this is `frontend/dist` in the repo), SPA rewrite `/*` → `/index.html`.

2. When prompted, set **`VITE_API_BASE`** to your API’s public URL (for example `https://nfl-stat-api.onrender.com`, no trailing slash).

3. Set **`CORS_ORIGINS`** on the API to your static site origin(s) (for example `https://nfl-stat-ui.onrender.com`). You can update this in the Render dashboard after the first deploy when URLs are known.

4. **Seed data on the persistent disk** (the disk starts empty). The API is configured with `DATA_LOCAL_DIR=/data` so both the app and the pipeline write to the same place. After seeding, **restart** the `nfl-stat-api` service so the in-memory player index reloads.

### Render post-deploy checklist (vs. generic “AI deploy” advice)

| Topic | This repo | Common mistake |
|--------|-----------|----------------|
| **Shell command** | With `rootDir: backend`, open **Shell** on `nfl-stat-api` and run: `python scripts/dataPipeline.py` | There is no `backend/data_pipeline.py`; the script is [`backend/scripts/dataPipeline.py`](backend/scripts/dataPipeline.py). |
| **Output path** | The pipeline reads **`DATA_LOCAL_DIR`** (set to `/data` in [`render.yaml`](render.yaml)), same as the API | Writing only under `backend/data` on the container disk would **not** land on the persistent volume. |
| **Serving Parquet** | [`main.py`](backend/main.py) already mounts `StaticFiles` at **`/data`** when `DATA_SOURCE=local` and the data directory exists | You do **not** need a second mount or `aiofiles` for basic file serving. |
| **Empty disk / first boot** | The API **starts** without `player_index.parquet`; `/health` reports `player_index_loaded: false` until you seed and restart | — |
| **Tuesday “cron on Render”** | A **Cron Job** is a **separate** service: it does **not** share the web service’s persistent disk, so `python …/dataPipeline.py` there would not update the API’s `/data` unless you upload elsewhere (e.g. R2) | For updates on the **same** disk, re-run the pipeline in **Shell** on the API and restart, or use **`DATA_SOURCE=r2`** and automate uploads to object storage. |
| **CORS** | Set **`CORS_ORIGINS`** to your static site origin (no trailing slash), e.g. `https://nfl-stat-ui.onrender.com` | Mismatch here shows up as browser “failed to fetch” / CORS errors. |
| **Frontend + DuckDB** | [`frontend/src/lib/api.ts`](frontend/src/lib/api.ts) uses **`VITE_API_BASE`**; shard URLs from the API are already absolute or rooted under that base | No need to hard-code `…/data/nfl_pbp_2024.parquet` unless you are experimenting. |

**Verify after seeding:** `ls /data` in Shell should list `player_index.parquet` and `nfl_pbp_*.parquet`. Hit `GET /health` and confirm `player_index_loaded` is `true` after restart.

**Alternative:** Skip the disk entirely — set **`DATA_SOURCE=r2`**, `PLAYER_INDEX_URL`, `PUBLIC_PBP_BASE`, and `PBP_YEARS` in the dashboard (and CORS on the bucket).

---

## Object storage (optional, `DATA_SOURCE=r2`)

1. Upload the same files as local `backend/data/`: `player_index.parquet`, `nfl_pbp_YYYY.parquet`.
2. Expose them over **HTTPS** (public bucket, custom domain, or worker). The values of `PLAYER_INDEX_URL` and `PUBLIC_PBP_BASE` must match how objects are reachable.
3. **CORS**: allow your **static site** origin for `GET` (and headers your browser sends for range requests if needed).

---

## Project layout

| Path | Role |
|------|------|
| `backend/main.py` | FastAPI app: `/health`, `/search`, `/player/{gsis_id}`, optional static `/data` |
| `backend/data/` | Local `player_index.parquet` and `nfl_pbp_*.parquet` |
| `backend/scripts/dataPipeline.py` | Downloads and builds Parquet from nflverse |
| `frontend/` | Vite + React + DuckDB-WASM workbench |
| `frontend/public/_redirects` | SPA fallback for hosts that honor `_redirects` |
| `render.yaml` | Render Blueprint (API + static site) |

---

## DuckDB-WASM / headers (optional)

If you enable **cross-origin isolation** (COOP/COEP) for threaded WASM, configure matching headers on your **static host** and ensure Parquet responses from object storage (or your CDN) satisfy **Cross-Origin Resource Policy** requirements. The default setup uses the non-COI bundle unless you change [`frontend/vite.config.ts`](frontend/vite.config.ts).
