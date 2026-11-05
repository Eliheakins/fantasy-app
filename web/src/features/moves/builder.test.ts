import { canPitch, copyText, pitchText } from "./builder";
import type { TradeEvaluation } from "@/features/trades/types";

const side = (name: string, before: number, after: number, who: "me" | "them") => ({
  side: who, roster_id: 1, team_name: name, playoff_before: before, playoff_after: after,
  title_before: 0.1, title_after: 0.1, wins_before: 8, wins_after: 8,
});
const result = (mine: number, theirs: number): TradeEvaluation => ({
  odds: [side("Mine", 0.5, 0.5 + mine, "me"), side("Rivals", 0.4, 0.4 + theirs, "them")],
  roster_changes: [], warning: null, trade_deadline: null, market: null,
});

describe("canPitch", () => {
  it("is true only when both sides gain playoff odds beyond noise", () => {
    expect(canPitch(result(0.03, 0.02))).toBe(true);
    expect(canPitch(result(0.03, -0.01))).toBe(false);
    expect(canPitch(result(-0.01, 0.03))).toBe(false);
    expect(canPitch(result(0.03, 0.0001))).toBe(false);
  });
  it("is false when a side is missing", () => {
    expect(canPitch({ ...result(0.03, 0.03), odds: [] })).toBe(false);
  });
});

describe("pitchText", () => {
  it("names the players and both teams' numbers", () => {
    const text = pitchText(result(0.03, 0.02), ["Chase Brown"], ["Tee Higgins"]);
    expect(text).toContain("Chase Brown");
    expect(text).toContain("Tee Higgins");
    expect(text).toContain("50.0% to 53.0%");
    expect(text).toContain("40.0% to 42.0%");
  });
});

describe("copyText", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("uses the clipboard when it works", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    expect(await copyText("hi")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hi");
  });
  it("falls back to execCommand when the clipboard is missing or rejects", async () => {
    const exec = vi.fn().mockReturnValue(true);
    document.execCommand = exec;
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("no")) } });
    expect(await copyText("hi")).toBe(true);
    expect(exec).toHaveBeenCalledWith("copy");
    vi.stubGlobal("navigator", {});
    expect(await copyText("hi")).toBe(true);
  });
  it("reports failure when nothing works", async () => {
    document.execCommand = vi.fn().mockReturnValue(false);
    vi.stubGlobal("navigator", {});
    expect(await copyText("hi")).toBe(false);
  });
});
