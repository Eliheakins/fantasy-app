import { describe, expect, it, vi } from "vitest";

import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { requestIntent } from "./nlqApi";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

describe("requestIntent", () => {
  it("sends X-Requested-With: fantasy-app, which the server requires on POST", async () => {
    mockFetch(200, { outcome: "unsupported", reason: "No." });

    await requestIntent("x", FIXTURE_SEASONS);

    const init = vi.mocked(fetch).mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("X-Requested-With")).toBe("fantasy-app");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  it("sends the generic league stat and never a league name", async () => {
    mockFetch(200, { outcome: "unsupported", reason: "No." });

    await requestIntent("Bijan fantasy points", FIXTURE_SEASONS);

    const body = String(vi.mocked(fetch).mock.calls[0]?.[1]?.body);
    expect(JSON.parse(body).stats.find((s: { id: string }) => s.id === "league_pts")).toMatchObject({
      label: "League points",
    });
    expect(body).not.toMatch(/colgate|yinz|1394105943137992704|1385108353306361856/i);
  });

  it("passes the abort signal to fetch and rejects when aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_, reject) => init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))),
      ),
    );
    const controller = new AbortController();

    const pending = requestIntent("x", FIXTURE_SEASONS, controller.signal);
    controller.abort();

    await expect(pending).rejects.toThrow();
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });

  it("returns a query outcome with the validated intent", async () => {
    mockFetch(200, {
      outcome: "query",
      intent: { stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" },
    });

    const outcome = await requestIntent("Mahomes passing yards 2023", FIXTURE_SEASONS);

    expect(outcome).toEqual({
      outcome: "query",
      intent: { stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" },
    });
  });

  it("returns an unsupported outcome with its reason", async () => {
    mockFetch(200, { outcome: "unsupported", reason: "Salaries are not in the data." });

    expect(await requestIntent("Mahomes salary", FIXTURE_SEASONS)).toEqual({
      outcome: "unsupported",
      reason: "Salaries are not in the data.",
    });
  });

  it("rejects an unsupported reason longer than the server allows", async () => {
    mockFetch(200, { outcome: "unsupported", reason: "x".repeat(301) });

    await expect(requestIntent("x", FIXTURE_SEASONS)).rejects.toThrow(/unexpected shape/);
  });

  it("rejects a reply that is neither shape", async () => {
    mockFetch(200, { stat_ids: ["pass_yards"] });

    await expect(requestIntent("x", FIXTURE_SEASONS)).rejects.toThrow(/unexpected shape/);
  });

  it("says the Ask service is not reachable and how to start it when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(requestIntent("x", FIXTURE_SEASONS)).rejects.toThrow(/Ask service is not reachable at .*make serve/);
  });

  it("surfaces the server's message on an error status", async () => {
    mockFetch(422, { detail: "I couldn't turn that into a query." });

    await expect(requestIntent("x", FIXTURE_SEASONS)).rejects.toThrow("I couldn't turn that into a query.");
  });
});
