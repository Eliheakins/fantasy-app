import { render, screen, within } from "@testing-library/react";
import { PositionalStrength } from "./PositionalStrength";
import { gradeGrid, ordinal } from "./logic";
import type { TeamGradeRow } from "./types";

const cell = (roster_id: number, team_name: string, position: string, rank: number, grade: string, over: Partial<TeamGradeRow> = {}): TeamGradeRow => ({
  roster_id, team_name, is_me: roster_id === 2, position, vor_per_week: 10 - rank, depth_per_week: 0.5, score: 1, rank, grade, ...over,
});
const rows = [
  cell(1, "Alpha", "overall", 2, "C"), cell(1, "Alpha", "QB", 1, "A"),
  cell(2, "Bravo", "overall", 1, "A"), cell(2, "Bravo", "QB", 3, "B", { vor_per_week: 5.5, depth_per_week: 1.25 }),
];

describe("gradeGrid", () => {
  it("sorts teams by overall rank and keeps cells by position", () => {
    const grid = gradeGrid(rows);
    expect(grid.map((t) => t.team_name)).toEqual(["Bravo", "Alpha"]);
    expect(grid[0]!.cells.QB?.grade).toBe("B");
  });
  it("puts a team with no overall row last", () => {
    expect(gradeGrid([cell(1, "A", "QB", 1, "A"), cell(2, "B", "overall", 1, "A")]).map((t) => t.team_name)).toEqual(["B", "A"]);
  });
});

describe("ordinal", () => {
  it.each([[1, "1st"], [2, "2nd"], [3, "3rd"], [4, "4th"], [11, "11th"], [12, "12th"], [21, "21st"], [112, "112th"]])("%i -> %s", (n, text) => {
    expect(ordinal(n)).toBe(text);
  });
});

describe("PositionalStrength", () => {
  it("orders teams by overall, shows grade with rank and marks the viewed team in text", () => {
    render(<PositionalStrength rows={rows} />);
    const body = screen.getAllByRole("row").slice(1);
    expect(within(body[0]!).getByText("Bravo (you)")).toBeInTheDocument();
    expect(within(body[1]!).getByText("Alpha")).toBeInTheDocument();
    expect(within(body[0]!).getByText("B")).toBeInTheDocument();
    expect(within(body[0]!).getByText("3rd")).toBeInTheDocument();
  });
  it("gives each bar an accessible starters and depth label", () => {
    render(<PositionalStrength rows={rows} />);
    expect(screen.getAllByRole("img", { name: "starters 5.5 pts/wk, depth 1.3 pts/wk" }).length).toBeGreaterThan(0);
  });
  it("shows a dash where a position has no row", () => {
    render(<PositionalStrength rows={[cell(1, "Alpha", "overall", 1, "A")]} />);
    expect(screen.getAllByText("–").length).toBeGreaterThan(0);
  });
});
