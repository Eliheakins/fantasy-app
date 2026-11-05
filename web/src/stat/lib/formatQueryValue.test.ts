import { formatQueryValue } from "./formatQueryValue";

describe("formatQueryValue", () => {
  it.each([
    [86.94117647, "86.9"], // per game
    [4183, "4183"],
    [5.4321, "5.43"],
    [0.12345, "0.123"], // per play and rates
    [-0.0456, "-0.046"],
    [-12.345, "-12.3"],
  ])("shows %s as %s", (value, text) => {
    expect(formatQueryValue(value)).toBe(text);
  });
  it("shows a dash for a missing value", () => {
    expect(formatQueryValue(null)).toBe("—");
    expect(formatQueryValue(undefined)).toBe("—");
  });
});
