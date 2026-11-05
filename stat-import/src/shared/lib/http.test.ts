import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { requestJson } from "./http";

const schema = z.object({ name: z.string(), count: z.number() });
const options = {
  what: "the widget list",
  unreachableHint: "Start it with: make serve",
  notFoundHint: "Build it first.",
  shapeHint: "Rebuild the data.",
};
const URL = "http://localhost:8100/data/widgets.json";

function respond(body: unknown, init: ResponseInit = { status: 200 }) {
  return vi.fn().mockResolvedValue(new Response(typeof body === "string" ? body : JSON.stringify(body), init));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("requestJson", () => {
  it("returns the response parsed by the schema", async () => {
    vi.stubGlobal("fetch", respond({ name: "a", count: 2 }));

    expect(await requestJson(URL, schema, options)).toEqual({ name: "a", count: 2 });
  });

  it("passes request options through", async () => {
    const fetchMock = respond({ name: "a", count: 2 });
    vi.stubGlobal("fetch", fetchMock);

    await requestJson(URL, schema, { ...options, init: { method: "POST", cache: "no-store" } });

    expect(fetchMock).toHaveBeenCalledWith(URL, { method: "POST", cache: "no-store" });
  });

  it("says what is unreachable, where, and how to fix it, instead of 'Failed to fetch'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await requestJson(URL, schema, options).catch((e: Error) => e);

    expect((error as Error).message).toBe(
      "The widget list is not reachable at http://localhost:8100, or the browser blocked the request (CORS). Start it with: make serve",
    );
  });

  it("lets an aborted request through untouched so callers can tell it from a failure", async () => {
    const abort = new DOMException("The operation was aborted.", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));

    await expect(requestJson(URL, schema, options)).rejects.toBe(abort);
  });

  it("turns a validation error list into its messages instead of raw JSON", async () => {
    vi.stubGlobal(
      "fetch",
      respond(
        {
          detail: [
            { type: "string_too_long", loc: ["body", "question"], msg: "String should have at most 2000 characters" },
          ],
        },
        { status: 422 },
      ),
    );

    await expect(requestJson(URL, schema, options)).rejects.toThrow("String should have at most 2000 characters");
  });

  it("explains a missing file with the hint for it", async () => {
    vi.stubGlobal("fetch", respond({ detail: "Not Found" }, { status: 404 }));

    await expect(requestJson(URL, schema, options)).rejects.toThrow(/not found.*Build it first\./);
  });

  it("uses the server's own message for other errors, and the status when there is none", async () => {
    vi.stubGlobal("fetch", respond({ detail: "Index not loaded." }, { status: 503 }));
    await expect(requestJson(URL, schema, options)).rejects.toThrow("Index not loaded.");

    vi.stubGlobal("fetch", respond("oops", { status: 500 }));
    await expect(requestJson(URL, schema, options)).rejects.toThrow(/failed \(500\)/);
  });

  it("explains a response that is not JSON instead of leaking a parse error", async () => {
    vi.stubGlobal("fetch", respond("<!doctype html><html></html>"));

    await expect(requestJson(URL, schema, options)).rejects.toThrow(/not JSON/);
  });

  it("names the first problem in plain words when the shape is wrong, on one line", async () => {
    vi.stubGlobal("fetch", respond({ name: "a", count: "many" }));

    const error = (await requestJson(URL, schema, options).catch((e: Error) => e)) as Error;

    expect(error.message).toMatch(/unexpected shape at "count"/);
    expect(error.message).toContain("Rebuild the data.");
    expect(error.message).not.toContain("\n");
  });
});
