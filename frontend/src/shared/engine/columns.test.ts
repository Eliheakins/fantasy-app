import { describe, expect, it, vi } from "vitest";

import { ColumnStore, normalizeColumn, type ColumnLoader, type ColumnSource } from "./columns";

const S22: ColumnSource = { year: 2022, url: "http://data/2022.parquet" };
const S23: ColumnSource = { year: 2023, url: "http://data/2023.parquet" };

const FILES: Record<string, Record<string, ArrayLike<unknown>>> = {
  [S22.url]: { a: [1, 2], b: ["x", "y"] },
  [S23.url]: { a: [3, null, 5], b: ["z", "w", "v"] },
};

function fakeLoader(): { load: ColumnLoader; calls: string[] } {
  const calls: string[] = [];
  const load: ColumnLoader = async (source, column) => {
    calls.push(`${source.year}:${column}`);
    const values = FILES[source.url]?.[column];
    if (!values) {
      throw new Error(`no column ${column}`);
    }
    return values;
  };
  return { load: vi.fn(load), calls };
}

describe("ColumnStore.table", () => {
  it("concatenates each column across sources in the order given", async () => {
    const store = new ColumnStore(fakeLoader().load);

    const table = await store.table([S22, S23], ["a", "b"]);

    expect(table.rowCount).toBe(5);
    expect(Array.from(table.cols.a!)).toEqual([1, 2, 3, null, 5]);
    expect(Array.from(table.cols.b!)).toEqual(["x", "y", "z", "w", "v"]);
  });

  it("loads each source and column once, and only the columns asked for", async () => {
    const { load, calls } = fakeLoader();
    const store = new ColumnStore(load);

    await store.table([S22, S23], ["a"]);
    await store.table([S23], ["a"]);
    await store.table([S22, S23], ["a", "b"]);

    expect(calls.sort()).toEqual(["2022:a", "2022:b", "2023:a", "2023:b"]);
  });

  it("keeps columns in a map without inherited keys, so no column name can resolve to a built-in", async () => {
    const table = await new ColumnStore(fakeLoader().load).table([S22], ["a"]);

    expect(Object.getPrototypeOf(table.cols)).toBeNull();
    expect("constructor" in table.cols).toBe(false);
  });

  it("returns an empty table for no sources", async () => {
    const table = await new ColumnStore(fakeLoader().load).table([], ["a"]);

    expect(table.rowCount).toBe(0);
    expect(Array.from(table.cols.a!)).toEqual([]);
  });

  it("keeps typed arrays typed when every source returns the same kind", async () => {
    const load: ColumnLoader = async (source) =>
      source.year === 2022 ? new Float64Array([1, 2]) : new Float64Array([3]);

    const table = await new ColumnStore(load).table([S22, S23], ["a"]);

    expect(table.cols.a).toBeInstanceOf(Float64Array);
    expect(Array.from(table.cols.a!)).toEqual([1, 2, 3]);
  });

  it("rejects columns of different lengths within one source", async () => {
    const load: ColumnLoader = async (_s, column) => (column === "a" ? [1, 2] : [1]);

    await expect(new ColumnStore(load).table([S22], ["a", "b"])).rejects.toThrow(/different lengths/);
  });

  it("does not cache a failed load, so the next query retries", async () => {
    let fail = true;
    const load: ColumnLoader = async () => {
      if (fail) {
        throw new Error("network down");
      }
      return [1];
    };
    const store = new ColumnStore(load);

    await expect(store.table([S22], ["a"])).rejects.toThrow("network down");
    fail = false;

    expect((await store.table([S22], ["a"])).rowCount).toBe(1);
  });

  it("rejects when the signal is already aborted", async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(new ColumnStore(fakeLoader().load).table([S22], ["a"], controller.signal)).rejects.toThrow();
  });
});

describe("normalizeColumn", () => {
  it("turns 64-bit integers into numbers", () => {
    expect(Array.from(normalizeColumn(new BigInt64Array([1n, 2n])))).toEqual([1, 2]);
    expect(normalizeColumn([1n, null, 3n])).toEqual([1, null, 3]);
  });

  it("leaves other columns alone", () => {
    const strings = ["a", null];
    const floats = new Float64Array([1.5]);

    expect(normalizeColumn(strings)).toBe(strings);
    expect(normalizeColumn(floats)).toBe(floats);
  });
});
