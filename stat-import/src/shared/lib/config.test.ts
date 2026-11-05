import { describe, expect, it } from "vitest";

import { dataUnreachableHint, joinUrl, resolveBaseUrls, START_API_HINT } from "./config";

describe("resolveBaseUrls", () => {
  it("defaults to the local API, with the data served from its /data folder", () => {
    expect(resolveBaseUrls({})).toEqual({
      apiBase: "http://localhost:8100",
      dataBase: "http://localhost:8100/data",
    });
  });

  it("derives the data location from a custom API location", () => {
    expect(resolveBaseUrls({ VITE_API_BASE_URL: "http://127.0.0.1:9000" }).dataBase).toBe("http://127.0.0.1:9000/data");
  });

  it("lets the data live on another host with no code change", () => {
    const urls = resolveBaseUrls({ VITE_DATA_BASE_URL: "https://cdn.example.com/nfl/v3/" });

    expect(urls.dataBase).toBe("https://cdn.example.com/nfl/v3");
    expect(urls.apiBase).toBe("http://localhost:8100");
  });

  it("treats an empty value as unset and drops trailing slashes", () => {
    const urls = resolveBaseUrls({ VITE_API_BASE_URL: "", VITE_DATA_BASE_URL: "https://cdn.example.com///" });

    expect(urls).toEqual({ apiBase: "http://localhost:8100", dataBase: "https://cdn.example.com" });
  });

  it("names the setting when a value is not an http(s) URL", () => {
    expect(() => resolveBaseUrls({ VITE_DATA_BASE_URL: "javascript:alert(1)" })).toThrow(/VITE_DATA_BASE_URL/);
    expect(() => resolveBaseUrls({ VITE_API_BASE_URL: "not a url" })).toThrow(/VITE_API_BASE_URL/);
  });
});

describe("base URLs that cannot be joined with a file name", () => {
  it("rejects a query string or fragment, which would end up in the middle of the path", () => {
    expect(() => resolveBaseUrls({ VITE_DATA_BASE_URL: "https://cdn.example.com/v3?sig=abc" })).toThrow(
      /VITE_DATA_BASE_URL.*query/,
    );
    expect(() => resolveBaseUrls({ VITE_API_BASE_URL: "http://localhost:8100#x" })).toThrow(/VITE_API_BASE_URL/);
  });
});

describe("dataUnreachableHint", () => {
  it("tells the user to start the API when the data comes from it", () => {
    expect(dataUnreachableHint({ apiBase: "http://localhost:8100", dataBase: "http://localhost:8100/data" })).toBe(
      START_API_HINT,
    );
  });

  it("points at the data host and its CORS and Range requirements when the data is elsewhere", () => {
    const hint = dataUnreachableHint({ apiBase: "http://localhost:8100", dataBase: "https://cdn.example.com/nfl" });

    expect(hint).toContain("https://cdn.example.com/nfl");
    expect(hint).toMatch(/CORS/);
    expect(hint).toMatch(/Range/);
    expect(hint).not.toContain("uvicorn");
  });
});

describe("joinUrl", () => {
  it("joins a base and a file name with exactly one slash", () => {
    expect(joinUrl("http://h/data", "manifest.json")).toBe("http://h/data/manifest.json");
    expect(joinUrl("http://h/data/", "/manifest.json")).toBe("http://h/data/manifest.json");
  });
});
