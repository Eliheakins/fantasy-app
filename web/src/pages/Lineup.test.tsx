import { type RenderResult, render as rtlRender, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";
import { LineupView } from "./Lineup";
import type { LineupRow, WinProbability } from "@/features/lineup/logic";

/** Player names link to Explore, which needs a router. */
const render = (ui: ReactElement): RenderResult => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

const row = (id: string, o: Partial<LineupRow> = {}): LineupRow => ({
  slot: "RB",
  gsis_id: id,
  full_name: `Player ${id}`,
  position: "RB",
  projection: 10,
  p10: 4,
  p90: 18,
  starting_now: true,
  recommended: true,
  injury: "Q",
  injury_note: "Questionable",
  locked: false,
  actual: 0,
  game: "Sun",
  change: "",
  ...o,
});
const cmp = (option: string) => ({ option, win_prob: 0.5, expected_points: 100, floor: 80, median: 100, ceiling: 120 });
const option = (name: string, o: Partial<WinProbability["options"][number]> = {}) =>
  ({
    option: name,
    win_prob: 0.5,
    expected_points: 131.2,
    floor: 90,
    median: 120,
    ceiling: 150,
    opp_floor: 85,
    opp_median: 115,
    opp_ceiling: 145,
    slot_calls: [],
    ...o,
  }) as WinProbability["options"][number];
const odds: WinProbability = {
  script: "You are a slight favourite",
  swap: { differs: false, players_in: [], players_out: [], text: null },
  comparison: [cmp("Expected points"), cmp("Win probability")],
  options: [option("win_prob")],
  lineups: {},
  summaries: { win_probability: { objective: "win_probability", shown_points: 10, sleeper_points: 10, gap: 0, win_prob: 0.5 } },
};

const differing: WinProbability = {
  ...odds,
  comparison: [cmp("Expected points"), cmp("Win probability"), { ...cmp("Max ceiling"), floor: 70, ceiling: 140 }],
};

const calls = [
  { slot: "FLEX", starter: "cook", alternative: "bern", share: 0.64 },
  { slot: "QB", starter: "qb", alternative: null, share: null },
  { slot: "RB", starter: "rb1", alternative: "bench", share: 0.9 },
];
const withCalls: WinProbability = { ...differing, options: [option("win_prob", { slot_calls: calls })] };
const cookRows = [
  row("cook", { full_name: "James Cook", slot: "FLEX", change: "Start", swap_in: "Ray Bernard" }),
  row("bern", { full_name: "Ray Bernard", recommended: false }),
  row("qb", { full_name: "Qb One", slot: "QB" }),
  row("rb1", { full_name: "Rb One" }),
];

describe("LineupView answer and evidence", () => {
  test("h1 is the answer and close calls get rows with a confidence word; clear slots collapse", () => {
    render(<LineupView base={cookRows} odds={withCalls} week={3} />);
    expect(screen.getByRole("heading", { level: 1, name: "Start James Cook at Flex" })).toBeTruthy();
    expect(screen.getByText("Flex: James Cook over Ray Bernard, better in 64% of simulations")).toBeTruthy();
    expect(screen.getByRole("button", { name: /lean.*what drives this/ })).toBeTruthy();
    expect(screen.getByText("2 slots are clear")).toBeTruthy();
    expect(screen.getByText(/Rb One over/).closest("details")).not.toHaveAttribute("open");
  });
  test("a late-scratch fallback is listed for the flagged starter", () => {
    render(<LineupView base={cookRows} odds={withCalls} week={3} />);
    expect(screen.getByText("If James Cook is out: start Ray Bernard")).toBeTruthy();
  });
  test("win probability is the starting pick, even as the underdog; the four-way switch sits under Other ways to pick", () => {
    const underdog = { ...withCalls, script: "Underdog (40% to win): variance helps" };
    render(<LineupView base={cookRows} odds={underdog} week={3} />);
    expect(screen.getByRole("radio", { name: "Win probability" })).toBeChecked();
    expect(screen.getByText("Other ways to pick").closest("details")).toContainElement(screen.getByRole("radiogroup"));
  });
  test("the answer uses the team total with K and DEF, the same one the range bars centre on", () => {
    render(<LineupView base={cookRows} odds={withCalls} week={3} />);
    expect(screen.getByText("131.2 points")).toBeTruthy();
  });
  test("no close slot, a slot with nobody eligible, and no panel without calls or fallbacks", () => {
    const clearOnly = { ...differing, options: [option("win_prob", { slot_calls: calls.slice(1) })] };
    const plain = [row("qb", { slot: "QB" }), row("rb1")];
    const { unmount } = render(<LineupView base={plain} odds={clearOnly} week={3} />);
    expect(screen.getByText("No slot is close.")).toBeTruthy();
    expect(screen.getByText("2 slots are clear")).toBeTruthy();
    expect(screen.getByText(/nobody eligible on the bench/)).toBeTruthy();
    unmount();
    render(<LineupView base={plain} odds={differing} week={3} />);
    expect(screen.queryByRole("heading", { name: "Close calls" })).toBeNull();
  });
  test("a missing simulation option leaves out the team scores", () => {
    render(<LineupView base={cookRows} odds={{ ...withCalls, options: [option("ceiling")] }} week={3} />);
    expect(screen.queryByRole("img", { name: /^Your team:/ })).toBeNull();
    expect(within(screen.getByRole("region", { name: "Your matchup" })).queryByText("Opponent, median")).toBeNull();
  });
  test("the tinted panel holds both team totals, the chance to win and the lineup against Sleeper", () => {
    render(<LineupView base={cookRows} odds={withCalls} week={3} />);
    const panel = screen.getByRole("region", { name: "Your matchup" });
    expect(panel.className).toContain("key-panel");
    expect(within(panel).getByText("You, median").nextElementSibling).toHaveTextContent("120.0");
    expect(within(panel).getByText("Opponent, median").nextElementSibling).toHaveTextContent("115.0");
    expect(within(panel).getByText("Chance to win")).toBeInTheDocument();
    expect(within(panel).getByText("Skill slots, shown vs Sleeper")).toBeInTheDocument();
    expect(within(panel).getByRole("img", { name: /^Your team:/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Close calls" }).closest("section")!.className).not.toContain("key-panel");
  });
  test("locked starters are not counted as clear slots", () => {
    const locked = cookRows.map((r) => (r.gsis_id === "rb1" ? { ...r, locked: true } : r));
    render(<LineupView base={locked} odds={withCalls} week={3} />);
    expect(screen.getByText("1 slot is clear")).toBeTruthy();
  });
  test("a finished week states the result and claims no clear slots", () => {
    const allLocked = cookRows.map((r) => ({ ...r, locked: true }));
    const side = (points: number, is_me: boolean) => ({ points, is_me }) as never;
    const board = [{ week: 3, matchup_id: 1, status: "Final", a: side(107.5, false), b: side(127.9, true) }] as never;
    render(<LineupView base={allLocked} odds={withCalls} week={3} board={board} />);
    expect(screen.getByRole("heading", { level: 1, name: "Week 3 is over: won 127.9 to 107.5" })).toBeTruthy();
    expect(screen.queryByText(/slots? (is|are) clear/)).toBeNull();
    const panel = screen.getByRole("region", { name: "Your matchup" });
    expect(within(panel).getByText("You, final").nextElementSibling).toHaveTextContent("127.9");
    expect(within(panel).getByText("Opponent, final").nextElementSibling).toHaveTextContent("107.5");
    expect(within(panel).getByText("Result").nextElementSibling).toHaveTextContent("Won by 20.4");
    expect(screen.queryByRole("img", { name: /^Your team:/ })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /Range/ })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Status" })).toBeNull();
    expect(screen.getAllByRole("columnheader", { name: "Points" }).length).toBeGreaterThan(0);
  });
  test("a manual pick stays when the matchup label changes", async () => {
    const underdog = { ...withCalls, script: "Underdog (40% to win): variance helps" };
    const { rerender } = render(<LineupView base={cookRows} odds={underdog} week={3} />);
    await userEvent.click(screen.getByRole("radio", { name: "Max floor" }));
    expect(screen.getByRole("radio", { name: "Max floor" })).toBeChecked();
    rerender(
      <MemoryRouter>
        <LineupView base={cookRows} odds={{ ...withCalls, script: "Favorite (70% to win): protect the floor" }} week={3} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("radio", { name: "Max floor" })).toBeChecked();
    rerender(
      <MemoryRouter>
        <LineupView base={cookRows} odds={{ ...withCalls, script: "Even matchup (50% to win)" }} week={3} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("radio", { name: "Max floor" })).toBeChecked();
  });
  test("range bars show both teams", () => {
    render(<LineupView base={cookRows} odds={withCalls} week={3} />);
    expect(screen.getByRole("img", { name: "Your team: Median 120.0, range 90.0 to 150.0" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Opponent: Median 115.0, range 85.0 to 145.0" })).toBeTruthy();
  });
});

describe("LineupView", () => {
  test("shows empty message with no rows", () => {
    render(<LineupView base={[]} odds={null} week={3} />);
    expect(screen.getByText(/No projections for week 3/)).toBeTruthy();
  });
  test("ok state without simulation shows tables and caveat but no objective switch", () => {
    render(<LineupView base={[row("a"), row("b", { recommended: false, locked: true })]} odds={null} week={0} />);
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.getByRole("heading", { name: "Bench" })).toBeTruthy();
    expect(screen.getAllByText("Locked").length).toBeGreaterThan(0);
    const injury = screen.getAllByText("Questionable");
    expect(injury.length).toBeGreaterThan(0);
    expect(injury[0]!.className).toContain("text-warning");
    expect(injury[0]!.className).not.toContain("border");
  });
  test("a table with no ranges drops the range column", () => {
    render(<LineupView base={[row("a", { p10: 10, p90: 10, locked: true })]} odds={null} week={0} />);
    expect(screen.queryByRole("columnheader", { name: /Range/ })).toBeNull();
  });
  test("one distinct lineup hides the switch and the table", () => {
    render(<LineupView base={[row("a")]} odds={odds} week={0} />);
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.getByText(/Every way of choosing picks this lineup/)).toBeTruthy();
    expect(screen.getByText(/No lineup change is recommended/)).toBeTruthy();
  });
  test("ok state with simulation shows switch, no-swap line and collapsed note", () => {
    render(<LineupView base={[row("a")]} odds={differing} week={0} />);
    expect(screen.getByRole("radiogroup")).toBeTruthy();
    expect(screen.getByText(/No lineup change is recommended/)).toBeTruthy();
    expect(screen.getByText(/share one row/)).toBeTruthy();
    expect(screen.getByText(/You are a slight favourite/)).toBeTruthy();
  });
  test("choosing an objective swaps in that objective's lineup", async () => {
    const withLineups: WinProbability = {
      ...differing,
      lineups: { max_ceiling: [row("z", { full_name: "Boom Player" })] },
    };
    render(<LineupView base={[row("a")]} odds={withLineups} week={0} />);
    expect(screen.queryByText("Boom Player")).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "Max ceiling" }));
    expect(screen.getAllByText("Boom Player").length).toBeGreaterThan(0);
    expect(screen.queryByText("Player a")).toBeNull();
  });
});
