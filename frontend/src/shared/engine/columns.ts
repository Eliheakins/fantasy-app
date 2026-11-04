import type { Columns } from "./expression";

/** One season's Parquet file: where it is and which season it holds. */
export interface ColumnSource {
  year: number;
  url: string;
}

/** Reads one column of one source. Implementations decide how (HTTP range requests, local files, test data). */
export type ColumnLoader = (source: ColumnSource, column: string) => Promise<ArrayLike<unknown>>;

export interface Table {
  rowCount: number;
  cols: Columns;
}

/** 64-bit integers arrive as BigInt; the metrics do plain number maths, so convert once on load. */
export function normalizeColumn(values: ArrayLike<unknown>): ArrayLike<unknown> {
  if (values instanceof BigInt64Array || values instanceof BigUint64Array) {
    return Float64Array.from(values, Number);
  }
  if (Array.isArray(values)) {
    const firstValue = values.find((v) => v !== null && v !== undefined);
    if (typeof firstValue === "bigint") {
      return values.map((v) => (typeof v === "bigint" ? Number(v) : v));
    }
  }
  return values;
}

type TypedArrayConstructor = new (length: number) => ArrayLike<unknown> & { set(source: ArrayLike<number>, offset: number): void };

/** Joins arrays end to end; typed arrays of one kind stay typed. A single part is returned as is. */
export function concatenate(parts: ArrayLike<unknown>[]): ArrayLike<unknown> {
  if (parts.length === 1) {
    return parts[0]!;
  }
  const total = parts.reduce((n, p) => n + p.length, 0);
  const first = parts[0];
  if (first && ArrayBuffer.isView(first) && parts.every((p) => p.constructor === first.constructor)) {
    const out = new (first.constructor as TypedArrayConstructor)(total);
    let offset = 0;
    for (const part of parts) {
      out.set(part as ArrayLike<number>, offset);
      offset += part.length;
    }
    return out;
  }
  const out: unknown[] = new Array<unknown>(total);
  let offset = 0;
  for (const part of parts) {
    for (let i = 0; i < part.length; i++) {
      out[offset++] = part[i];
    }
  }
  return out;
}

/**
 * Loads columns lazily, one source and one column at a time, and keeps each so a later query reuses
 * it. A query asks for exactly the columns it reads, so most of a 59-column shard is never fetched.
 */
export class ColumnStore {
  private readonly cache = new Map<string, Promise<ArrayLike<unknown>>>();

  constructor(private readonly loader: ColumnLoader) {}

  private column(source: ColumnSource, column: string): Promise<ArrayLike<unknown>> {
    const key = `${source.url}\u0000${column}`;
    let pending = this.cache.get(key);
    if (!pending) {
      pending = this.loader(source, column).then(normalizeColumn);
      this.cache.set(key, pending);
      // A failed load must not be remembered, or one network blip would stick until reload.
      pending.catch(() => {
        if (this.cache.get(key) === pending) {
          this.cache.delete(key);
        }
      });
    }
    return pending;
  }

  /** The requested columns across `sources`, concatenated in the order given. */
  async table(sources: ColumnSource[], columns: string[], signal?: AbortSignal): Promise<Table> {
    signal?.throwIfAborted();
    const wanted = [...new Set(columns)];
    const perSource = await Promise.all(
      sources.map(async (source) => {
        const loaded = await Promise.all(wanted.map((c) => this.column(source, c)));
        if (new Set(loaded.map((c) => c.length)).size > 1) {
          throw new Error(`Columns in ${source.url} have different lengths; the file may be corrupt.`);
        }
        return loaded;
      }),
    );
    signal?.throwIfAborted();

    const cols: Columns = {};
    wanted.forEach((name, k) => {
      cols[name] = concatenate(perSource.length === 0 ? [[]] : perSource.map((loaded) => loaded[k]!));
    });
    const rowCount = perSource.reduce((n, loaded) => n + (loaded[0]?.length ?? 0), 0);
    return { rowCount, cols };
  }
}
