import { layoutRange, rangeLabel, sharedDomain } from "./rangeAxis";

describe("sharedDomain", () => {
  it("spans every row with 5% padding", () => {
    const d = sharedDomain([
      { p10: 10, p50: 15, p90: 20 },
      { p10: 0, p50: 5, p90: 10 },
    ]);
    expect(d).toEqual([-1, 21]);
  });
  it("ignores missing ends and returns null with no numbers", () => {
    expect(sharedDomain([{ p50: 4 }, { p10: null, p90: 8 }])).toEqual([3.8, 8.2]);
    expect(sharedDomain([{}, { p50: null }])).toBeNull();
  });
  it("widens a single-value domain", () => {
    expect(sharedDomain([{ p50: 5 }])).toEqual([4, 6]);
  });
});

describe("layoutRange", () => {
  const domain = [0, 100] as const;
  it("maps p10, p90 and median onto the same axis for every row", () => {
    const a = layoutRange({ p10: 20, p50: 50, p90: 80 }, domain, 200);
    expect(a.bar).toEqual({ x1: 40, x2: 160 });
    expect(a.tick).toBe(100);
  });
  it("clamps values outside the domain", () => {
    const r = layoutRange({ p10: -50, p50: 50, p90: 500 }, domain, 200);
    expect(r.bar).toEqual({ x1: 0, x2: 200 });
  });
  it("draws only the tick when an end is missing", () => {
    expect(layoutRange({ p10: null, p50: 50, p90: 80 }, domain, 200)).toEqual({ bar: null, tick: 100 });
    expect(layoutRange({ p50: 50, p10: 10 }, domain, 200).bar).toBeNull();
  });
  it("draws only the bar when the median is missing", () => {
    const r = layoutRange({ p10: 10, p90: 30 }, domain, 100);
    expect(r.tick).toBeNull();
    expect(r.bar).toEqual({ x1: 10, x2: 30 });
  });
  it("swaps reversed ends", () => {
    expect(layoutRange({ p10: 80, p90: 20 }, domain, 100).bar).toEqual({ x1: 20, x2: 80 });
  });
});

describe("rangeLabel", () => {
  it("reads like the spec", () => {
    expect(rangeLabel({ p10: 12.1, p50: 17.2, p90: 23.4 })).toBe("Median 17.2, range 12.1 to 23.4");
  });
  it("covers missing ends and no data", () => {
    expect(rangeLabel({ p50: 17.2 })).toBe("Median 17.2, range unavailable");
    expect(rangeLabel({})).toBe("No projection");
  });
});
