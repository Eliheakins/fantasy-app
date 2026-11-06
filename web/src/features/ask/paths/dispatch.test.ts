import { describe, expect, test, vi } from "vitest";
import { dispatchAsk } from "./dispatch";
import { ASK_PATHS } from "./index";
import type { AskActions, AskInput, AskPath } from "./types";

const input: AskInput = { question: "q", dictionary: [], seasons: [2024], chipGroups: [], signal: new AbortController().signal };
const actions: AskActions = { fail: vi.fn(), answer: vi.fn(), showStartSit: vi.fn(), showTrade: vi.fn(), showRoute: vi.fn(), choose: vi.fn() };
const never = () => false;

const fake = (id: AskPath["id"], match: unknown, calls: string[]): AskPath => ({
  id,
  read: () => {
    calls.push(`read:${id}`);
    return match;
  },
  answer: () => void calls.push(`answer:${id}`),
});

describe("ASK_PATHS", () => {
  test("lists start/sit, trade, fantasy routes, rules, then the model catch-all", () => {
    expect(ASK_PATHS.map((p) => p.id)).toEqual(["start_sit", "trade", "route", "rules", "model"]);
  });
});

describe("dispatchAsk", () => {
  test("lets the first path that matches answer and skips the rest", async () => {
    const calls: string[] = [];
    const paths = [fake("start_sit", null, calls), fake("trade", { x: 1 }, calls), fake("rules", { y: 1 }, calls)];
    await dispatchAsk(input, actions, never, paths);
    expect(calls).toEqual(["read:start_sit", "read:trade", "answer:trade"]);
  });

  test("answers nothing when no path matches", async () => {
    const calls: string[] = [];
    await dispatchAsk(input, actions, never, [fake("rules", null, calls)]);
    expect(calls).toEqual(["read:rules"]);
  });

  test("stops without answering when the ask went stale during a read", async () => {
    const calls: string[] = [];
    await dispatchAsk(input, actions, () => true, [fake("trade", { x: 1 }, calls), fake("rules", { y: 1 }, calls)]);
    expect(calls).toEqual(["read:trade"]);
  });

  test("rejects when a read fails, so the caller shows one message", async () => {
    const boom: AskPath = { id: "model", read: () => Promise.reject(new Error("model is down")), answer: vi.fn() };
    await expect(dispatchAsk(input, actions, never, [boom])).rejects.toThrow("model is down");
  });
});
