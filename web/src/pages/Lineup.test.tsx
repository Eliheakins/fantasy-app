import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";
import { LineupView } from "./Lineup";
import type { LineupRow, WinProbability } from "@/features/lineup/logic";

const row = (id: string, o: Partial<LineupRow> = {}): LineupRow => ({
  slot: "RB", gsis_id: id, full_name: `Player ${id}`, position: "RB", projection: 10, p10: 4, p90: 18,
  starting_now: true, recommended: true, injury: "Q", injury_note: "Questionable", locked: false, actual: 0, game: "Sun", change: "", ...o,
});
const cmp = (option: string) => ({ option, win_prob: 0.5, expected_points: 100, floor: 80, median: 100, ceiling: 120 });
const odds: WinProbability = {
  script: "You are a slight favourite",
  swap: { differs: false, players_in: [], players_out: [], text: null },
  comparison: [cmp("Expected points"), cmp("Win probability")],
  options: [{ option: "max_points" } as WinProbability["options"][number]],
  lineups: {},
  summaries: { expected_points: { objective: "expected_points", shown_points: 10, sleeper_points: 10, gap: 0, win_prob: 0.5 } },
};

const differing: WinProbability = {
  ...odds,
  comparison: [cmp("Expected points"), cmp("Win probability"), { ...cmp("Max ceiling"), floor: 70, ceiling: 140 }],
};

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
    expect(screen.getAllByText("Questionable").length).toBeGreaterThan(0);
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
    expect(screen.getByText("You are a slight favourite")).toBeTruthy();
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
