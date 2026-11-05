import { describe, expect, it } from "vitest";

import { API_BASE, DATA_BASE_URL, joinUrl, START_API_HINT } from "./config";

describe("base URLs", () => {
  it("default to the stat routes of the fantasy API on the same origin", () => {
    expect(API_BASE).toBe("/api/stat");
    expect(DATA_BASE_URL).toBe("/api/stat/data");
  });

  it("tell the user to start the app, with no uvicorn or CORS advice", () => {
    expect(START_API_HINT).toBe("Start it with: make serve");
  });
});

describe("joinUrl", () => {
  it("joins a base and a file name with exactly one slash", () => {
    expect(joinUrl("http://h/data", "manifest.json")).toBe("http://h/data/manifest.json");
    expect(joinUrl("http://h/data/", "/manifest.json")).toBe("http://h/data/manifest.json");
    expect(joinUrl(DATA_BASE_URL, "manifest.json")).toBe("/api/stat/data/manifest.json");
  });
});
