import { describe, expect, it } from "vitest";

import { type AskState, askReducer, initialAsk, shownOf, type Shown } from "./askReducer";
import type { FantasyRoute } from "./fantasyRoute";

const route = { kind: "route", value: { text: "See Moves" } as unknown as FantasyRoute } satisfies Shown;
const showing: AskState = { phase: "idle", question: "q", message: null, shown: route };

describe("askReducer", () => {
  it("starts idle with the URL's question and nothing shown", () => {
    expect(initialAsk("who won")).toEqual({ phase: "idle", question: "who won", message: null, shown: null });
  });

  it("clears the message and any shown answer when an ask starts", () => {
    const failed = askReducer(showing, { type: "fail", text: "no" });
    expect(askReducer(failed, { type: "start" })).toEqual({ phase: "working", question: "q", message: null });
  });

  it("keeps a shown answer when the URL moves to its own question, and drops it otherwise", () => {
    expect(askReducer(showing, { type: "urlChanged", question: "q", keepShown: true })).toEqual(showing);
    const moved = askReducer(showing, { type: "urlChanged", question: "other", keepShown: false });
    expect(moved).toEqual({ phase: "idle", question: "other", message: null, shown: null });
  });

  it("drops namesake choices when the URL changes mid-choice", () => {
    const choosing = askReducer(initialAsk("q"), { type: "choose", resolved: [], choices: [] });
    expect(choosing.phase).toBe("choosing");
    expect(askReducer(choosing, { type: "urlChanged", question: "q", keepShown: true })).toEqual(initialAsk("q"));
  });

  it("asks for text without leaving the current phase", () => {
    const working = askReducer(initialAsk(""), { type: "start" });
    expect(askReducer(working, { type: "needText" })).toEqual({ ...working, message: "Type a question first." });
  });

  it("edits the question in any phase", () => {
    const working = askReducer(initialAsk("a"), { type: "start" });
    expect(askReducer(working, { type: "edit", question: "b" })).toEqual({ ...working, question: "b" });
  });

  it("reads a shown answer only while idle and only of its kind", () => {
    expect(shownOf(showing, "route")).toBe(route.value);
    expect(shownOf(showing, "trade")).toBeNull();
    expect(shownOf(askReducer(showing, { type: "start" }), "route")).toBeNull();
    expect(shownOf(askReducer(showing, { type: "answered" }), "route")).toBeNull();
  });
});
