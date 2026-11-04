import { describe, expect, it } from "vitest";

import { describeStartupError } from "./startupError";

describe("describeStartupError", () => {
  it("is null when nothing failed", () => {
    expect(describeStartupError(null, null)).toBeNull();
  });

  it("passes a manifest error through unchanged", () => {
    expect(describeStartupError("No data manifest found.", null)).toBe("No data manifest found.");
  });

  it("labels an engine error so it is not mistaken for a data problem", () => {
    expect(describeStartupError(null, "wasm failed")).toBe("DuckDB failed to start: wasm failed");
  });

  it("reports both when both failed, instead of hiding one", () => {
    expect(describeStartupError("No data manifest found.", "wasm failed")).toBe(
      "No data manifest found. DuckDB failed to start: wasm failed",
    );
  });
});
