import { possessive } from "./text";

describe("possessive", () => {
  it("handles names that end in s, trailing space and empty", () => {
    expect(possessive("Chris")).toBe("Chris'");
    expect(possessive("Eli")).toBe("Eli's");
    expect(possessive("Chris ")).toBe("Chris'");
    expect(possessive("")).toBe("");
  });
});
