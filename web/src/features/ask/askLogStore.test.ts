import { afterEach, describe, expect, it, vi } from "vitest";
import { logAsk, readLog } from "./askLogStore";

afterEach(() => {
  window.localStorage.clear();
});

describe("logAsk", () => {
  it("still logs with an id where crypto.randomUUID is missing (plain http)", () => {
    vi.stubGlobal("crypto", {});

    const id = logAsk({ question: "q", path: "none", outcome: { kind: "message", text: "t" } });

    expect(id).toBeTruthy();
    expect(readLog().map((e) => e.id)).toEqual([id]);
  });
  it("gives each entry its own id", () => {
    vi.stubGlobal("crypto", {});
    const a = logAsk({ question: "a", path: "none", outcome: { kind: "message", text: "t" } });
    const b = logAsk({ question: "b", path: "none", outcome: { kind: "message", text: "t" } });
    expect(a).not.toBe(b);
  });
});
