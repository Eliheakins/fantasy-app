/// <reference lib="webworker" />
/**
 * Placeholder worker entry for projects that want a **classic** DuckDB bootstrap.
 *
 * Production setup uses `initDB()` in `duckdb.ts`, which follows the official Vite pattern:
 * `new Worker(bundle.mainWorker!, { type: "module" })` with `?url` imports from `@duckdb/duckdb-wasm`.
 *
 * To use `new Worker(new URL("./duckdb.worker.ts", import.meta.url), { type: "classic" })`,
 * replace this file with a classic worker that calls `importScripts()` on the URL from
 * `import mvp from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url"` (MVP bundle only).
 */
export {};
