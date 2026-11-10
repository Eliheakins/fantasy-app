import { describe, expect, it } from "vitest";
import { clampedLinear } from "./linearMap";

describe("clampedLinear", () => {
  it("maps the domain ends and midpoint onto the range", () => {
    const x = clampedLinear([0, 10], [0, 100]);
    expect([x(0), x(5), x(10)]).toEqual([0, 50, 100]);
  });

  it("clamps values outside the domain to the range ends", () => {
    const x = clampedLinear([0, 10], [20, 120]);
    expect([x(-5), x(15)]).toEqual([20, 120]);
  });

  it("handles a reversed range", () => {
    const x = clampedLinear([0, 10], [100, 0]);
    expect([x(0), x(2.5), x(10), x(99)]).toEqual([100, 75, 0, 0]);
  });

  it("puts everything mid-range for a zero-width domain", () => {
    expect(clampedLinear([3, 3], [0, 100])(7)).toBe(50);
  });
});
