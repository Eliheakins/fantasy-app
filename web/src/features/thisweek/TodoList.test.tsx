import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { TodoList } from "./TodoList";
import type { Todo } from "./todos";

const todo = (over: Partial<Todo>): Todo => ({
  id: "x",
  leagueKey: "a",
  leagueName: "Colgate",
  kind: "lineup",
  title: "Start Y",
  detail: "Lineup",
  href: "/lineup?league=a",
  effect: { playoffPoints: null, points: null },
  deadlineDay: null,
  sleeperUrl: "https://sleeper.com/leagues/9",
  ...over,
});

const show = (todos: Todo[]) =>
  render(
    <MemoryRouter>
      <TodoList todos={todos} />
    </MemoryRouter>,
  );

describe("TodoList Sleeper link", () => {
  it("links to the league in Sleeper, named by league", () => {
    show([todo({})]);
    const a = screen.getByRole("link", { name: /Open Colgate in Sleeper/ });
    expect(a).toHaveAttribute("href", "https://sleeper.com/leagues/9");
    expect(a).toHaveAttribute("target", "_blank");
  });
  it("has no Sleeper link when the league id is missing", () => {
    show([todo({ sleeperUrl: null })]);
    expect(screen.queryByRole("link", { name: /Sleeper/ })).toBeNull();
  });
});

describe("TodoList fill-ins", () => {
  it("renders fill-ins as a nested list with the claim note", () => {
    show([todo({ kind: "cover", fillIns: ["Add A (5.0 pts), drop B", "Add C (4.0 pts)"] })]);
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Add A (5.0 pts), drop B")).toBeInTheDocument();
    expect(screen.getByText(/it may need a waiver claim/)).toBeInTheDocument();
  });
  it("says no free agent is left when the list is empty", () => {
    show([todo({ kind: "cover", fillIns: [] })]);
    expect(screen.getByText("No free agent left to start this week")).toBeInTheDocument();
  });
});
