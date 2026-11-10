import { afterEach, beforeEach } from "vitest";
import { buildStrip, stripNotes, etDay, lineupDeadlineDay, waiverDeadlineDay, weekDays } from "./weekLogic";

// Wed 4 Nov 2026, 10:00 in New York (15:00 UTC)
const WED = new Date("2026-11-04T15:00:00Z");

describe("etDay and weekDays", () => {
  it("uses the New York date, not the UTC one", () => {
    expect(etDay(new Date("2026-11-05T02:00:00Z"))).toBe("2026-11-04");
  });
  it("runs Tuesday to Monday around today", () => {
    expect(weekDays(WED)).toEqual(["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"]);
  });
  it("starts a new week on Tuesday morning, after Monday night", () => {
    expect(weekDays(new Date("2026-11-10T09:00:00Z"))[0]).toBe("2026-11-10");
    expect(weekDays(new Date("2026-11-10T03:00:00Z"))[0]).toBe("2026-11-03"); // still Mon night in New York
  });
});

describe("deadlines", () => {
  it("puts the waiver clear on its weekday this week, or next week once it has passed", () => {
    expect(waiverDeadlineDay(2, new Date("2026-11-03T15:00:00Z"))).toBe("2026-11-04"); // Tue: Wed ahead
    expect(waiverDeadlineDay(2, WED)).toBe("2026-11-04"); // clear day itself is still today
    expect(waiverDeadlineDay(2, new Date("2026-11-06T15:00:00Z"))).toBe("2026-11-11"); // Fri: next Wed
    expect(waiverDeadlineDay(null, WED)).toBeNull();
  });
  it("uses the next kickoff still to come for lineups", () => {
    const kickoffs = [
      { team: "A", kickoff: "2026-11-05T20:15:00-05:00" },
      { team: "B", kickoff: "2026-11-08T13:00:00-05:00" },
    ];
    expect(lineupDeadlineDay(kickoffs, WED)).toBe("2026-11-05");
    expect(lineupDeadlineDay(kickoffs, new Date("2026-11-06T15:00:00Z"))).toBe("2026-11-08");
    expect(lineupDeadlineDay(kickoffs, new Date("2026-11-09T15:00:00Z"))).toBeNull();
    expect(lineupDeadlineDay([], WED)).toBeNull();
  });
});

describe("buildStrip", () => {
  const calendar = {
    week: 9,
    kickoffs: [
      { team: "A", kickoff: "2026-11-05T20:15:00-05:00" },
      { team: "B", kickoff: "2026-11-05T20:15:00-05:00" },
      { team: "C", kickoff: "2026-11-08T13:00:00-05:00" },
      { team: "D", kickoff: "2026-11-08T13:00:00-05:00" },
    ],
    waivers: [{ league_key: "a", name: "Alpha", day_of_week: 2, daily: false }],
  };

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("marks today with the fake clock and carries waiver, injury report and kickoff events", () => {
    vi.setSystemTime(WED);
    const strip = buildStrip(new Date(), calendar);
    expect(strip.map((d) => d.isToday)).toEqual([false, true, false, false, false, false, false]);
    expect(strip.map((d) => d.label)).toEqual(["Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon"]);
    const text = (i: number) => strip[i]?.events.map((e) => e.text);
    expect(text(1)).toEqual(["Waivers clear: Alpha"]);
    expect(text(2)).toEqual(["1 game, first 8:15 PM"]);
    expect(text(3)).toEqual(["Injury report"]);
    expect(text(5)).toEqual(["1 game, first 1:00 PM"]);
  });

  it("lists daily or unknown waiver timing as unavailable instead of placing it", () => {
    const daily = { ...calendar, waivers: [{ league_key: "a", name: "Alpha", day_of_week: null, daily: true }] };
    const strip = buildStrip(WED, daily);
    expect(strip.flatMap((d) => d.events).some((e) => e.kind === "waivers")).toBe(false);
  });

  it("shows only the injury report when the calendar has nothing else", () => {
    const strip = buildStrip(WED, { week: null, kickoffs: [], waivers: [] });
    expect(strip.flatMap((d) => d.events).map((e) => e.kind)).toEqual(["injury"]);
  });
});

describe("daylight saving and waiver day mapping", () => {
  it("keeps seven calendar days across the clock change on Sun 1 Nov 2026", () => {
    const days = weekDays(new Date("2026-11-01T18:00:00Z"));
    expect(days).toEqual(["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"]);
    expect(etDay(new Date("2026-11-01T04:30:00Z"))).toBe("2026-11-01"); // 00:30 EDT
    expect(etDay(new Date("2026-11-02T04:30:00Z"))).toBe("2026-11-01"); // 23:30 EST, still Sunday
  });
  it("maps Sleeper's Monday 0 and Sunday 6 onto the Tuesday to Monday strip", () => {
    const tue = new Date("2026-11-03T15:00:00Z");
    expect(waiverDeadlineDay(0, tue)).toBe("2026-11-09"); // Monday: last day of the strip
    expect(waiverDeadlineDay(6, tue)).toBe("2026-11-08"); // Sunday
    expect(waiverDeadlineDay(1, tue)).toBe("2026-11-03"); // Tuesday
  });
});

describe("kickoffs the strip cannot show", () => {
  const base = { week: 8, waivers: [] };
  it("explains when every kickoff is outside the strip, and counts teams with no time", () => {
    const notes = stripNotes(WED, {
      ...base,
      kickoffs: [
        { team: "A", kickoff: "2026-11-01T13:00:00-05:00" },
        { team: "B", kickoff: null },
      ],
    });
    expect(notes[0]).toMatch(/All kickoffs for week 8 are outside/);
    expect(notes[1]).toMatch(/1 teams have no kickoff time/);
  });
  it("is quiet when every kickoff is inside", () => {
    expect(stripNotes(WED, { ...base, kickoffs: [{ team: "A", kickoff: "2026-11-08T13:00:00-05:00" }] })).toEqual([]);
  });
  it("ignores a team with no time when placing kickoffs", () => {
    const strip = buildStrip(WED, { ...base, kickoffs: [{ team: "A", kickoff: null }] });
    expect(strip.flatMap((d) => d.events).map((e) => e.kind)).toEqual(["injury"]);
  });
});
