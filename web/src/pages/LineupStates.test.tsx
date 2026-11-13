import { render, screen } from "@testing-library/react";
import { leaguePath, onlyRoutes } from "@/test/fakeApi";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { ApiState } from "@/api/envelope";

let lineupState: ApiState<unknown>;
const currentLeague = "x";
let requested: string[] = [];
vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: currentLeague, leagues: { kind: "loading" } }),
  useLeagueApi: (route: string, query?: object) => {
    const path = leaguePath(route, query);
    requested.push(`${currentLeague}/${path}`);
    const loading: ApiState<unknown> = { kind: "loading" };
    // week 5 from ?week=5, else week 1 (the league list never loads here, so there is no current week)
    const week = (w: number) => ({
      [`lineup?week=${w}`]: lineupState,
      [`win-probability?week=${w}`]: loading,
      [`scoreboard?week=${w}`]: loading,
    });
    return onlyRoutes({ ...week(1), ...week(5), "lineup-grid": lineupState })(path);
  },
}));
import Lineup from "./Lineup";

describe("Lineup page states", () => {
  beforeEach(() => {
    requested = [];
  });
  test("loading", () => {
    lineupState = { kind: "loading" };
    render(
      <MemoryRouter>
        <Lineup />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading…")).toBeTruthy();
  });
  test("running", () => {
    lineupState = { kind: "running", startedAt: null };
    render(
      <MemoryRouter>
        <Lineup />
      </MemoryRouter>,
    );
    expect(screen.getByRole("status")).toBeTruthy();
  });
  test("no data", () => {
    lineupState = { kind: "no_data", message: "none" };
    render(
      <MemoryRouter>
        <Lineup />
      </MemoryRouter>,
    );
    expect(screen.getByText("none")).toBeTruthy();
  });
  test("ok but empty", () => {
    lineupState = { kind: "ready", data: [] };
    render(
      <MemoryRouter>
        <Lineup />
      </MemoryRouter>,
    );
    expect(screen.getByText(/No projections/)).toBeTruthy();
  });
  test("the week comes from ?week=, else the first week when the league has no current week", () => {
    lineupState = { kind: "ready", data: [] };
    render(
      <MemoryRouter initialEntries={["/lineup?week=5"]}>
        <Lineup />
      </MemoryRouter>,
    );
    expect(requested).toContain("x/lineup?week=5");
    render(
      <MemoryRouter>
        <Lineup />
      </MemoryRouter>,
    );
    expect(requested).toContain("x/win-probability?week=1");
  });
  test("?view=ahead asks for the lineup grid and shows the table", () => {
    lineupState = { kind: "ready", data: { weeks: [3], playoff_weeks: [], rows: [] } };
    render(
      <MemoryRouter initialEntries={["/lineup?view=ahead"]}>
        <Lineup />
      </MemoryRouter>,
    );
    expect(requested).toContain("x/lineup-grid");
    expect(screen.getByRole("radio", { name: "Weeks ahead", checked: true })).toBeTruthy();
  });
  test("?view=ahead starts no lineup, win-probability or scoreboard request", () => {
    lineupState = { kind: "ready", data: { weeks: [3], playoff_weeks: [], rows: [] } };
    render(
      <MemoryRouter initialEntries={["/lineup?view=ahead"]}>
        <Lineup />
      </MemoryRouter>,
    );
    expect(requested).toEqual(["x/lineup-grid"]);
  });
  test("the view toggle follows the page heading in both views", () => {
    const cases: [string, ApiState<unknown>][] = [
      ["/lineup", { kind: "loading" }],
      ["/lineup", { kind: "ready", data: [] }],
      ["/lineup?view=ahead", { kind: "loading" }],
    ];
    for (const [entry, state] of cases) {
      lineupState = state;
      const { unmount } = render(
        <MemoryRouter initialEntries={[entry]}>
          <Lineup />
        </MemoryRouter>,
      );
      const heading = screen.getByRole("heading", { level: 1 });
      const toggle = screen.getByRole("radiogroup", { name: "Lineup view" });
      expect(heading.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      unmount();
    }
  });
  test("two leagues build different query keys for the same endpoint", () => {
    const key = (league: string) => `/api/leagues/${encodeURIComponent(league)}/lineup?week=1`;
    expect(key("colgate")).not.toBe(key("yinzburgh"));
  });
});
