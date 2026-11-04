import { afterEach, describe, expect, it, vi } from "vitest";

import { requestIntent } from "./nlqApi";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("requestIntent", () => {
  it("returns a query outcome with the validated intent", async () => {
    mockFetch(200, {
      outcome: "query",
      intent: { stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" },
    });

    const outcome = await requestIntent("Mahomes passing yards 2023");

    expect(outcome).toEqual({
      outcome: "query",
      intent: { stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" },
    });
  });

  it("returns an unsupported outcome with its reason", async () => {
    mockFetch(200, { outcome: "unsupported", reason: "Salaries are not in the data." });

    expect(await requestIntent("Mahomes salary")).toEqual({
      outcome: "unsupported",
      reason: "Salaries are not in the data.",
    });
  });

  it("rejects an unsupported reason longer than the server allows", async () => {
    mockFetch(200, { outcome: "unsupported", reason: "x".repeat(301) });

    await expect(requestIntent("x")).rejects.toThrow(/Unexpected \/nlq\/intent response/);
  });

  it("rejects a reply that is neither shape", async () => {
    mockFetch(200, { stat_ids: ["pass_yards"] });

    await expect(requestIntent("x")).rejects.toThrow(/Unexpected \/nlq\/intent response/);
  });

  it("surfaces the server's message on an error status", async () => {
    mockFetch(422, { detail: "I couldn't turn that into a query." });

    await expect(requestIntent("x")).rejects.toThrow("I couldn't turn that into a query.");
  });
});
