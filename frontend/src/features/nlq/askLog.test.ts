import { describe, expect, it } from "vitest";

import {
  appendEntry,
  type AskLogEntry,
  isNewEdit,
  loadLog,
  type LoggedQuery,
  MAX_LOG_ENTRIES,
  recordCorrection,
  saveLog,
  toEvalCases,
} from "./askLog";

const query = (over: Partial<LoggedQuery> = {}): LoggedQuery => ({
  players: ["00-0033873"],
  stats: ["pass_yards"],
  filters: ["season-2023"],
  granularity: "total",
  order: null,
  limit: null,
  split: null,
  ...over,
});

const entry = (id: string, over: Partial<AskLogEntry> = {}): AskLogEntry => ({
  id,
  at: "2026-11-04T12:00:00.000Z",
  question: `question ${id}`,
  path: "rules",
  outcome: { kind: "answered", query: query() },
  corrected: null,
  ...over,
});

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key: string) => data[key] ?? null,
    setItem: (key: string, value: string) => {
      data[key] = value;
    },
  };
}

describe("appendEntry", () => {
  it("puts the newest first and leaves the input alone", () => {
    const before = [entry("a")];

    const after = appendEntry(before, entry("b"));

    expect(after.map((e) => e.id)).toEqual(["b", "a"]);
    expect(before.map((e) => e.id)).toEqual(["a"]);
  });

  it("keeps only the newest entries once the cap is passed", () => {
    const full = Array.from({ length: MAX_LOG_ENTRIES }, (_, i) => entry(`old${i}`));

    const after = appendEntry(full, entry("new"));

    expect(after).toHaveLength(MAX_LOG_ENTRIES);
    expect(after[0]?.id).toBe("new");
    expect(after.at(-1)?.id).toBe(`old${MAX_LOG_ENTRIES - 2}`);
  });
});

describe("recordCorrection", () => {
  it("stores the corrected query on the entry", () => {
    const fixed = query({ filters: ["season-2022"] });

    const after = recordCorrection([entry("a")], "a", fixed);

    expect(after[0]?.corrected).toEqual(fixed);
  });

  it("clears the correction when the query is put back to the answer", () => {
    const corrected = recordCorrection([entry("a")], "a", query({ filters: [] }));

    const restored = recordCorrection(corrected, "a", query());

    expect(restored[0]?.corrected).toBeNull();
  });

  it("changes nothing for an unknown id or an entry that was not an answer", () => {
    const message = entry("m", { outcome: { kind: "message", text: "no" } });
    const entries = [entry("a"), message];

    expect(recordCorrection(entries, "zzz", query())).toEqual(entries);
    expect(recordCorrection(entries, "m", query())).toEqual(entries);
  });
});

describe("isNewEdit", () => {
  it("is false for an answer shown as given, even after an edit to an earlier answer", () => {
    expect(isNewEdit(null, "b", "answer", "answer")).toBe(false);
    expect(isNewEdit({ id: "a", key: "edited" }, "b", "answer", "answer")).toBe(false);
  });

  it("is true for a change, and false again once that change is logged", () => {
    expect(isNewEdit(null, "b", "answer", "edited")).toBe(true);
    expect(isNewEdit({ id: "b", key: "edited" }, "b", "answer", "edited")).toBe(false);
    expect(isNewEdit({ id: "b", key: "edited" }, "b", "answer", "answer")).toBe(true);
  });
});

describe("loadLog and saveLog", () => {
  it("round-trips entries", () => {
    const storage = memoryStorage();
    const entries = [entry("b", { corrected: query({ stats: ["pass_tds"] }) }), entry("a")];

    saveLog(storage, entries);

    expect(loadLog(storage)).toEqual(entries);
  });

  it("reads an entry logged before splits existed as having none", () => {
    const { split: _split, ...old } = query();
    const storage = memoryStorage({ "bridge.askLog.v1": JSON.stringify([{ ...entry("a"), outcome: { kind: "answered", query: old } }]) });

    const [loaded] = loadLog(storage);

    expect(loaded?.outcome.kind === "answered" && loaded.outcome.query.split).toBeNull();
  });

  it("is empty when nothing was saved or the saved text is not JSON", () => {
    expect(loadLog(memoryStorage())).toEqual([]);
    expect(loadLog(memoryStorage({ "bridge.askLog.v1": "{nope" }))).toEqual([]);
  });

  it("keeps the valid entries and drops the malformed ones", () => {
    const storage = memoryStorage({
      "bridge.askLog.v1": JSON.stringify([entry("ok"), { id: "bad" }, "junk"]),
    });

    expect(loadLog(storage).map((e) => e.id)).toEqual(["ok"]);
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

    expect(loadLog(broken)).toEqual([]);
    expect(() => saveLog(broken, [entry("a")])).not.toThrow();
  });
});

describe("toEvalCases", () => {
  it("turns each corrected answer into an eval case with the corrected stats, filters and granularity", () => {
    const corrected = query({ stats: ["pass_tds"], filters: ["season-2022"], granularity: "per_game" });

    const cases = toEvalCases([entry("a", { question: "Mahomes TDs 2022", corrected }), entry("b")]);

    expect(cases).toEqual([
      { q: "Mahomes TDs 2022", stats: ["pass_tds"], filters: ["season-2022"], granularity: "per_game" },
    ]);
  });

  it("skips leaderboards, which the eval format cannot express", () => {
    const board = query({ players: [], order: { metric: "pass_yards", direction: "desc" }, limit: 10 });

    expect(toEvalCases([entry("a", { corrected: board })])).toEqual([]);
  });
});
