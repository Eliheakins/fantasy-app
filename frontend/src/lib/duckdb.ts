import * as duckdb from "@duckdb/duckdb-wasm";

import type { QueryResult } from "@/types/workbench";

/** Arrow table surface used by `tableToRows` (avoids importing broken `apache-arrow` package exports in TS). */
type ArrowTableLike = {
  schema: { fields: Array<{ name: string }> };
  numRows: number | bigint;
  getChild: (name: string) => { get: (i: number) => unknown } | null | undefined;
};

import duckdbEhWasm from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import duckdbEhWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbMvpWasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import duckdbMvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdbCoiWasm from "@duckdb/duckdb-wasm/dist/duckdb-coi.wasm?url";
import duckdbCoiPthread from "@duckdb/duckdb-wasm/dist/duckdb-browser-coi.pthread.worker.js?url";
import duckdbCoiWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-coi.worker.js?url";

/** Matches `@duckdb/duckdb-wasm` bundle keys (`coi` = cross-origin isolation / pthreads). */
export type DuckDBBundleKind = "mvp" | "eh" | "coi";

const MANUAL_BUNDLES: duckdb.DuckDBBundles = {
  mvp: {
    mainModule: duckdbMvpWasm,
    mainWorker: duckdbMvpWorker,
  },
  eh: {
    mainModule: duckdbEhWasm,
    mainWorker: duckdbEhWorker,
  },
  coi: {
    mainModule: duckdbCoiWasm,
    mainWorker: duckdbCoiWorker,
    pthreadWorker: duckdbCoiPthread,
  },
};

function duckBundlesForChoice(bundle: DuckDBBundleKind): duckdb.DuckDBBundles {
  const out: duckdb.DuckDBBundles = { mvp: MANUAL_BUNDLES.mvp };
  if (bundle === "eh") {
    out.eh = MANUAL_BUNDLES.eh;
  }
  if (bundle === "coi") {
    out.coi = MANUAL_BUNDLES.coi;
  }
  return out;
}

let dbInstance: duckdb.AsyncDuckDB | null = null;
let connection: duckdb.AsyncDuckDBConnection | null = null;
let initPromise: Promise<void> | null = null;
let activeBundle: DuckDBBundleKind = "mvp";

function tableToRows(table: ArrowTableLike): QueryResult {
  const columns = table.schema.fields.map((f) => f.name);
  const rows: Record<string, unknown>[] = [];
  const n = Number(table.numRows);
  for (let i = 0; i < n; i++) {
    const row: Record<string, unknown> = {};
    for (const name of columns) {
      const col = table.getChild(name);
      row[name] = col?.get(i) ?? null;
    }
    rows.push(row);
  }
  return { rows, columns };
}

function getDb(): duckdb.AsyncDuckDB {
  if (!dbInstance) {
    throw new Error("DuckDB not initialized; call initDB() first.");
  }
  return dbInstance;
}

async function getConnection(): Promise<duckdb.AsyncDuckDBConnection> {
  const db = getDb();
  if (!connection) {
    connection = await db.connect();
  }
  return connection;
}

/**
 * Initialize DuckDB-WASM once (safe under React Strict Mode via shared `initPromise`).
 * Uses Vite `?url` assets and `new Worker(bundle.mainWorker!)` per upstream docs.
 *
 * Alternate entry (MVP classic worker only):
 * `new Worker(new URL("./duckdb.worker.ts", import.meta.url), { type: "classic" })`
 */
export function initDB(bundle: DuckDBBundleKind = "mvp"): Promise<void> {
  if (initPromise) {
    return initPromise;
  }

  initPromise = (async () => {
    if (dbInstance) {
      return;
    }

    activeBundle = bundle;
    const selected = await duckdb.selectBundle(duckBundlesForChoice(bundle));
    const worker = new Worker(selected.mainWorker!, { type: "module" });
    const logger = new duckdb.ConsoleLogger();
    const db = new duckdb.AsyncDuckDB(logger, worker);
    await db.instantiate(selected.mainModule, selected.pthreadWorker);
    dbInstance = db;
  })();

  return initPromise;
}

/**
 * Register a remote Parquet URL and expose it as a view `tableName` (safe identifier).
 */
export async function mountRemoteShard(url: string, tableName: string): Promise<void> {
  const db = getDb();
  const safeView = sanitizeIdentifier(tableName);
  const logicalFile = `${safeView}.parquet`;

  await db.registerFileURL(
    logicalFile,
    url,
    duckdb.DuckDBDataProtocol.HTTP,
    false,
  );

  const conn = await getConnection();
  await conn.query(
    `CREATE OR REPLACE VIEW "${safeView}" AS SELECT * FROM read_parquet('${logicalFile}');`,
  );
}

function sanitizeIdentifier(raw: string): string {
  const s = raw.replace(/[^a-zA-Z0-9_]/g, "_").replace(/^([0-9])/, "_$1");
  return s.length > 0 ? s : "shard";
}

/**
 * Run SQL and return rows as plain objects (Arrow table → JSON-friendly rows).
 */
export async function runQuery(sql: string): Promise<QueryResult> {
  const conn = await getConnection();
  const table = (await conn.query(sql)) as ArrowTableLike;
  return tableToRows(table);
}

export function getActiveBundle(): DuckDBBundleKind {
  return activeBundle;
}
