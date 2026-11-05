import { describe, expect, it } from "vitest";

import {
  cacheKey,
  catalogSignature,
  forgetCorrection,
  lookupIntent,
  MAX_CACHE_ENTRIES,
  normalizeQuestion,
  readIntentCache,
  storeIntent,
} from "./intentCache";

const INTENT = { stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" as const };

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem: (key: string) => data[key] ?? null,
    setItem: (key: string, value: string) => {
      data[key] = value;
    },
  };
}

describe("normalizeQuestion", () => {
  it("ignores case, punctuation and extra spaces", () => {
    expect(normalizeQuestion("  Mahomes' passing   YARDS, 2023?! ")).toBe(
      normalizeQuestion("mahomes passing yards 2023"),
    );
  });

  it("keeps different questions apart", () => {
    expect(normalizeQuestion("mahomes yards 2023")).not.toBe(normalizeQuestion("mahomes yards 2022"));
  });
});

describe("catalogSignature and cacheKey", () => {
  const catalog = { stats: [{ id: "pass_yards" }, { id: "pass_tds" }], filters: [{ id: "season-2023" }] };

  it("is the same for the same ids in any order", () => {
    const shuffled = { stats: [{ id: "pass_tds" }, { id: "pass_yards" }], filters: [{ id: "season-2023" }] };

    expect(catalogSignature(shuffled)).toBe(catalogSignature(catalog));
  });

  it("changes when a stat or a chip is added, so an old answer is not reused for a new catalog", () => {
    const grown = { ...catalog, filters: [...catalog.filters, { id: "season-2024" }] };

    expect(catalogSignature(grown)).not.toBe(catalogSignature(catalog));
    expect(cacheKey(catalogSignature(grown), "q")).not.toBe(cacheKey(catalogSignature(catalog), "q"));
  });
});

describe("storeIntent and lookupIntent", () => {
  it("returns what was stored under the same key", () => {
    const storage = memoryStorage();

    storeIntent(storage, "k", { intent: INTENT, source: "model" });

    expect(lookupIntent(readIntentCache(storage), "k")).toEqual({ intent: INTENT, source: "model" });
    expect(lookupIntent(readIntentCache(storage), "other")).toBeUndefined();
  });

  it("lets a correction replace a model answer, but not the other way round", () => {
    const storage = memoryStorage();
    const fixed = { ...INTENT, filter_ids: ["season-2022"] };

    storeIntent(storage, "k", { intent: INTENT, source: "model" });
    storeIntent(storage, "k", { intent: fixed, source: "correction" });
    storeIntent(storage, "k", { intent: INTENT, source: "model" });

    expect(lookupIntent(readIntentCache(storage), "k")).toEqual({ intent: fixed, source: "correction" });
  });

  it("forgets the oldest entries past the cap", () => {
    const storage = memoryStorage();

    for (let i = 0; i <= MAX_CACHE_ENTRIES; i++) {
      storeIntent(storage, `k${i}`, { intent: INTENT, source: "model" });
    }
    const cache = readIntentCache(storage);

    expect(Object.keys(cache)).toHaveLength(MAX_CACHE_ENTRIES);
    expect(lookupIntent(cache, "k0")).toBeUndefined();
    expect(lookupIntent(cache, `k${MAX_CACHE_ENTRIES}`)).toBeDefined();
  });

  it("starts empty when the saved text is damaged or has entries of the wrong shape", () => {
    expect(readIntentCache(memoryStorage({ "bridge.intentCache.v1": "{nope" }))).toEqual({});
    const wrong = memoryStorage({ "bridge.intentCache.v1": JSON.stringify({ k: { intent: { stat_ids: [] } } }) });

    expect(lookupIntent(readIntentCache(wrong), "k")).toBeUndefined();
  });

  it("does not throw when the storage is unavailable", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };

    expect(readIntentCache(broken)).toEqual({});
    expect(() => storeIntent(broken, "k", { intent: INTENT, source: "model" })).not.toThrow();
  });
});

describe("forgetCorrection", () => {
  it("removes a saved correction so the question is read afresh", () => {
    const storage = memoryStorage();
    storeIntent(storage, "k", { intent: INTENT, source: "correction" });
    storeIntent(storage, "other", { intent: INTENT, source: "correction" });

    forgetCorrection(storage, "k");

    expect(lookupIntent(readIntentCache(storage), "k")).toBeUndefined();
    expect(lookupIntent(readIntentCache(storage), "other")).toBeDefined();
  });

  it("keeps a model answer, which a reverted edit says nothing about", () => {
    const storage = memoryStorage();
    storeIntent(storage, "k", { intent: INTENT, source: "model" });

    forgetCorrection(storage, "k");

    expect(lookupIntent(readIntentCache(storage), "k")?.source).toBe("model");
  });
});
