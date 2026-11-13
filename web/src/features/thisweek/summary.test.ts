import { summaryText, type SummaryLeague } from "./summary";
import type { Todo } from "./todos";

const league = (name: string, over: Partial<SummaryLeague> = {}): SummaryLeague => ({
  name,
  lastWeek: {
    week: 9,
    roster_id: 1,
    team_name: "Me",
    opponent: "Rivals",
    points: 120.54,
    opp_points: 98.2,
    result: "W",
    bench_points_left: null,
    luck: null,
  },
  odds: {
    roster_id: 1,
    team_name: "Me",
    is_me: true,
    as_of_week: 10,
    prev_as_of_week: 9,
    p_playoffs: 0.58,
    p_title: 0.1,
    d_playoffs: 0.08,
    d_title: -0.01,
  },
  phase: "season",
  failed: false,
  ...over,
});
const todo = (title: string, over: Partial<Todo> = {}): Todo => ({
  id: title,
  leagueKey: "1234567890123456789",
  leagueName: "Alpha",
  kind: "waiver",
  title,
  detail: "Waivers",
  href: "/moves?league=1234567890123456789",
  effect: { playoffPoints: 2.3, points: 1.5 },
  deadlineDay: null,
  sleeperUrl: "https://sleeper.com/leagues/1234567890123456789",
  ...over,
});
const lines = (text: string) => text.split("\n");

describe("summaryText", () => {
  it("gives the result, odds and the to-dos with their effect, by league name", () => {
    const text = summaryText([league("Alpha"), league("Beta", { lastWeek: null })], [todo("Add Coleman")]);
    expect(text).toContain("Alpha: W 120.5 to 98.2 vs Rivals (week 9)");
    expect(text).toContain("Beta: no result yet");
    expect(text).toContain("Alpha: playoff odds 58% (+8 points)");
    expect(text).toContain("1. Add Coleman (Alpha): +2.3 playoff pts, +1.5 points");
  });
  it("says a league whose digest failed could not load, not that it has no result yet", () => {
    const text = summaryText([league("Alpha", { lastWeek: null, odds: null, failed: true })], []);
    expect(text).toContain("Alpha: could not load");
    expect(text).not.toContain("no result yet");
  });
  it("uses title odds in the playoffs and says so when out", () => {
    expect(summaryText([league("Alpha", { phase: "playoffs" })], [])).toContain("Alpha: title odds 10% (-1 points)");
    expect(summaryText([league("Alpha", { phase: "out" })], [])).toContain("Alpha: out of the playoffs");
  });
  it("stays between 5 and 8 lines, with or without to-dos", () => {
    const two = [league("Alpha"), league("Beta")];
    expect(lines(summaryText(two, [])).length).toBe(5);
    const many = Array.from({ length: 20 }, (_, i) => todo(`Do ${i}`));
    expect(lines(summaryText(two, many)).length).toBe(8);
    expect(lines(summaryText(two, [todo("One")])).length).toBeGreaterThanOrEqual(5);
  });
  it("never carries ids, urls or ranks", () => {
    const text = summaryText([league("Alpha")], [todo("Add Coleman")]);
    expect(text).not.toMatch(/\d{15,}/);
    expect(text).not.toContain("http");
    expect(text).not.toContain("ECR");
  });
});
