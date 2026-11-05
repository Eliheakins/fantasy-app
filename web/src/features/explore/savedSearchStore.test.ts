import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addSaved, readSaved, removeSaved, savedHref, writeSaved } from "./savedSearchStore";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("saved searches", () => {
  it("saves the query without league, team and week, under a trimmed name", () => {
    const list = addSaved([], "  Top WRs ", "?league=a&team=2&week=5&p=00-1&s=rec_yards");
    expect(list).toEqual([{ name: "Top WRs", query: "p=00-1&s=rec_yards" }]);
  });

  it("replaces a search with the same name and ignores a blank name", () => {
    const one = addSaved([], "A", "?s=x");
    expect(addSaved(one, "A", "?s=y")).toEqual([{ name: "A", query: "s=y" }]);
    expect(addSaved(one, "   ", "?s=y")).toEqual(one);
  });

  it("deletes by name", () => {
    expect(removeSaved([{ name: "A", query: "s=x" }, { name: "B", query: "s=y" }], "A")).toEqual([{ name: "B", query: "s=y" }]);
  });

  it("re-runs on Find players with the current league, team and week", () => {
    expect(savedHref({ name: "A", query: "s=x&p=1" }, "?league=L&team=3&week=7&s=other")).toBe("/players/find?s=x&p=1&league=L&team=3&week=7");
  });

  it("round-trips through localStorage and drops malformed entries", () => {
    expect(writeSaved([{ name: "A", query: "s=x" }])).toBe(true);
    expect(readSaved()).toEqual([{ name: "A", query: "s=x" }]);
    window.localStorage.setItem("fantasy.savedSearches", JSON.stringify([{ name: "A", query: "s=x" }, { name: 3 }, "x"]));
    expect(readSaved()).toEqual([{ name: "A", query: "s=x" }]);
    window.localStorage.setItem("fantasy.savedSearches", "{not json");
    expect(readSaved()).toEqual([]);
  });

  it("works without storage: reads empty and reports a failed write instead of throwing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    expect(readSaved()).toEqual([]);
    expect(writeSaved([{ name: "A", query: "s=x" }])).toBe(false);
  });
});
