import { beforeEach } from "vitest";
import { type OddsRun, newAdds, oddsSince, readVisit, writeVisit } from "./visit";

beforeEach(() => window.localStorage.clear());

describe("last visit storage", () => {
  it("is null on a first visit and returns what was written, per league", () => {
    expect(readVisit("a")).toBeNull();
    writeVisit("a", { at: "2026-11-01T10:00:00.000Z", adds: ["X"] });
    expect(readVisit("a")).toEqual({ at: "2026-11-01T10:00:00.000Z", adds: ["X"] });
    expect(readVisit("b")).toBeNull();
  });

  it("ignores a stored value that is not a visit", () => {
    window.localStorage.setItem("fantasy.lastVisit.a", "{not json");
    expect(readVisit("a")).toBeNull();
    window.localStorage.setItem("fantasy.lastVisit.a", JSON.stringify({ at: 5 }));
    expect(readVisit("a")).toBeNull();
    window.localStorage.setItem("fantasy.lastVisit.a", JSON.stringify({ at: "not a date", adds: [] }));
    expect(readVisit("a")).toBeNull();
  });

  it("works when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readVisit("a")).toBeNull();
    expect(() => writeVisit("a", { at: "2026-11-01T10:00:00.000Z", adds: [] })).not.toThrow();
  });
});

describe("oddsSince", () => {
  const run = (run_at: string, p_playoffs: number | null, p_title: number | null, roster_id = 1): OddsRun => ({
    run_at,
    roster_id,
    p_playoffs,
    p_title,
  });
  const history = [run("2026-10-30T10:00:00", 0.5, 0.1), run("2026-10-30T10:00:00", 0.9, 0.5, 2), run("2026-11-02T10:00:00", 0.58, 0.09)];

  it("compares my latest run with my last run at or before the last visit, in percentage points", () => {
    const c = oddsSince(history, 1, "2026-11-01T00:00:00Z");
    expect(c?.playoffs).toBeCloseTo(8);
    expect(c?.title).toBeCloseTo(-1);
  });
  it("is null with no earlier run, no newer run or no history", () => {
    expect(oddsSince(history, 1, "2026-10-01T00:00:00Z")).toBeNull();
    expect(oddsSince(history, 1, "2026-11-03T00:00:00Z")).toBeNull();
    expect(oddsSince([], 1, "2026-11-01T00:00:00Z")).toBeNull();
  });
  it("keeps a missing value null, not zero", () => {
    const c = oddsSince([run("2026-10-30T10:00:00", null, 0.1), run("2026-11-02T10:00:00", 0.5, 0.2)], 1, "2026-11-01T00:00:00Z");
    expect(c?.playoffs).toBeNull();
    expect(c?.title).toBeCloseTo(10);
  });
});

describe("newAdds", () => {
  it("lists current adds the last visit did not have", () => {
    expect(newAdds(["A", "B", "C"], ["B"])).toEqual(["A", "C"]);
  });
  it("shows nothing when the last visit stored no list or nothing is new", () => {
    expect(newAdds(["A"], undefined)).toEqual([]);
    expect(newAdds(["A"], ["A", "Z"])).toEqual([]);
  });
});
