import { describe, expect, test } from "vitest";
import type { LineupRow } from "./logic";
import {
  type SlotCall,
  callText,
  recommendedObjective,
  scratchFallbacks,
  splitCalls,
  startAnswer,
  winnerShare,
  weekOverText,
  weekResult,
  resultText,
} from "./calls";
import type { ScoreboardRow } from "@/lib/scoreboard";

const call = (slot: string, share: number | null, o: Partial<SlotCall> = {}): SlotCall => ({
  slot,
  starter: `s-${slot}`,
  alternative: share === null ? null : `b-${slot}`,
  share,
  ...o,
});
const row = (id: string, name: string, o: Partial<LineupRow> = {}): LineupRow => ({
  slot: "FLEX",
  gsis_id: id,
  full_name: name,
  position: "RB",
  projection: 10,
  p10: 4,
  p90: 18,
  starting_now: false,
  recommended: true,
  injury: null,
  injury_note: null,
  locked: false,
  actual: 0,
  game: "",
  change: "",
  ...o,
});

describe("close calls", () => {
  test("only lean and toss-up slots are close; clear slots and slots with no alternative collapse", () => {
    const { close, clear } = splitCalls(
      [call("QB", 0.9), call("FLEX", 0.64), call("WR", 0.5), call("TE", null), call("RB", 0.7)],
      new Set(),
    );
    expect(close.map((c) => c.slot)).toEqual(["FLEX", "WR"]);
    expect(clear.map((c) => c.slot)).toEqual(["QB", "TE", "RB"]);
  });
  test("a locked slot is settled, not a clear call", () => {
    const { close, clear } = splitCalls([call("QB", null), call("RB", 0.9)], new Set(["s-QB"]));
    expect(close).toEqual([]);
    expect(clear.map((c) => c.slot)).toEqual(["RB"]);
  });
  test("a slot with nobody eligible says so", () => {
    expect(callText(call("TE", null), { "s-TE": "Kelce" })).toBe("TE: Kelce, nobody eligible on the bench");
  });
  test("below 50% the text never says better; the confidence is for the side that wins more", () => {
    const names = { "s-FLEX": "Cook", "b-FLEX": "Bernard" };
    expect(callText(call("FLEX", 0.4), names, "upside")).toBe(
      "Flex: Cook over Bernard for the upside; Bernard scores more in 60% of simulations",
    );
    expect(callText(call("FLEX", 0.3), names, "floor")).toBe(
      "Flex: Cook over Bernard for the floor; Bernard scores more in 70% of simulations",
    );
    expect(callText(call("FLEX", 0.4), names)).toBe("Flex: Cook over Bernard; Bernard scores more in 60% of simulations");
    expect(winnerShare(call("FLEX", 0.3))).toBe(0.7);
    expect(winnerShare(call("FLEX", 0.64))).toBe(0.64);
  });
  test("text names both players and the share", () => {
    const names = { "s-FLEX": "James Cook", "b-FLEX": "Ray Bernard" };
    expect(callText(call("FLEX", 0.64), names)).toBe("Flex: James Cook over Ray Bernard, better in 64% of simulations");
  });
});

describe("late scratch fallbacks", () => {
  test("lists each recommended starter that has a swap_in, skipping bench rows", () => {
    const rows = [
      row("a", "James Cook", { swap_in: "Ray Bernard", injury: "Questionable" }),
      row("b", "Solid", { swap_in: null }),
      row("c", "Benched", { recommended: false, swap_in: "Nobody" }),
    ];
    expect(scratchFallbacks(rows)).toEqual([{ gsisId: "a", text: "If James Cook is out: start Ray Bernard" }]);
  });
});

describe("recommended objective", () => {
  test("is win probability whatever the matchup", () => {
    expect(recommendedObjective()).toBe("win_probability");
  });
});

describe("the answer", () => {
  test("names the starts against Sleeper, or says the lineup is set", () => {
    const start = row("a", "James Cook", { change: "Start", slot: "FLEX" });
    expect(startAnswer([start, row("b", "Other")], true)).toBe("Start James Cook at Flex");
    expect(startAnswer([row("b", "Other")], true)).toBe("Your lineup is set");
    expect(startAnswer([row("b", "Other")], false)).toBe("Your best lineup");
  });
});

describe("a finished week", () => {
  const side = (points: number, is_me: boolean) => ({ points, is_me }) as ScoreboardRow["a"];
  const board = (status: ScoreboardRow["status"], me: number, them: number): ScoreboardRow[] => [
    { week: 8, matchup_id: 1, status, a: side(them, false), b: side(me, true) } as ScoreboardRow,
  ];
  test("states the result plainly", () => {
    expect(weekOverText(8, board("Final", 127.9, 107.5))).toBe("Week 8 is over: won 127.9 to 107.5");
    expect(weekOverText(8, board("Final", 100, 107.5))).toBe("Week 8 is over: lost 100.0 to 107.5");
    expect(weekOverText(8, board("Final", 100, 100))).toBe("Week 8 is over: tied 100.0 to 100.0");
    expect(resultText(weekResult(board("Final", 127.9, 107.5))!)).toBe("Won by 20.4");
    expect(resultText(weekResult(board("Final", 100, 107.5))!)).toBe("Lost by 7.5");
    expect(resultText(weekResult(board("Final", 100, 100))!)).toBe("Tied");
  });
  test("is null while games are left or without a scoreboard", () => {
    expect(weekOverText(8, board("Live", 1, 2))).toBeNull();
    expect(weekOverText(8, [])).toBeNull();
    expect(weekOverText(8, null)).toBeNull();
  });
});
