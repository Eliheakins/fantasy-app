import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { type LineupGrid, WeeksAheadGrid } from "./WeeksAheadGrid";

const cellRow = (week: number, slot: string, over: Partial<LineupGrid["rows"][number]> = {}) => ({
  week,
  slot,
  gsis_id: `${slot}${week}`,
  full_name: `${slot} Player ${week}`,
  points: 10,
  flag: null,
  ...over,
});
const grid: LineupGrid = {
  weeks: [14, 15],
  playoff_weeks: [15],
  rows: [
    cellRow(14, "QB"),
    cellRow(14, "WR", { flag: "weak", points: 6.5 }),
    cellRow(15, "QB", { flag: "bye", gsis_id: null, full_name: null, points: 0 }),
    cellRow(15, "WR", { flag: "out" }),
  ],
};
const show = (g: LineupGrid = grid) =>
  render(
    <MemoryRouter>
      <WeeksAheadGrid grid={g} league="colgate" />
    </MemoryRouter>,
  );

describe("WeeksAheadGrid", () => {
  it("is a native table with a caption, week column headers and slot row headers", () => {
    show();
    const table = screen.getByRole("table", { name: /weeks ahead/i });
    const cols = within(table).getAllByRole("columnheader");
    expect(cols.map((c) => c.getAttribute("scope"))).toEqual(["col", "col", "col"]);
    const rows = within(table).getAllByRole("rowheader");
    expect(rows.map((r) => [r.textContent, r.getAttribute("scope")])).toEqual([
      ["QB", "row"],
      ["WR", "row"],
    ]);
  });
  it("marks playoff weeks and the current week in text", () => {
    show();
    expect(screen.getByRole("columnheader", { name: /Week 15.*playoffs/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Week 14.*this week/ })).toBeInTheDocument();
  });
  it("shows the starter and points in each cell", () => {
    show();
    expect(screen.getByText("QB Player 14")).toBeInTheDocument();
    expect(screen.getByText("6.5")).toBeInTheDocument();
  });
  it("shows a visible text flag with a link to Moves filtered by position", () => {
    show();
    const link = screen.getByRole("link", { name: /Find a WR for week 14/ });
    expect(link).toHaveAttribute("href", "/moves?league=colgate&pos=WR");
    expect(screen.getByText("Weak")).toBeVisible();
    expect(screen.getByText("Bye")).toBeVisible();
    expect(screen.getByText("Out")).toBeVisible();
    expect(screen.getByRole("link", { name: /Find a QB for week 15/ })).toBeInTheDocument();
  });
  it("links a flex slot to every skill position it takes", () => {
    show({ ...grid, rows: [cellRow(14, "FLEX", { flag: "weak" })] });
    expect(screen.getByRole("link", { name: /Find a FLEX for week 14/ })).toHaveAttribute("href", "/moves?league=colgate");
  });
  it("puts the scroll wrapper in the tab order with a label", () => {
    show();
    const wrap = screen.getByRole("region", { name: /weeks ahead/i });
    expect(wrap).toHaveAttribute("tabindex", "0");
  });
  it("says the season is over when no weeks remain", () => {
    show({ weeks: [], playoff_weeks: [], rows: [] });
    expect(screen.getByText("Season over")).toBeInTheDocument();
  });
});
