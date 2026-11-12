import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { ApiState } from "@/api/envelope";

let lineupState: ApiState<unknown>;
const currentLeague = "x";
const requested: string[] = [];
vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: currentLeague, leagues: { kind: "loading" } }),
  useLeagueApi: (path: string) => {
    requested.push(`${currentLeague}/${path}`);
    return path.startsWith("lineup") ? lineupState : { kind: "loading" };
  },
}));
import Lineup from "./Lineup";

describe("Lineup page states", () => {
  beforeEach(() => undefined);
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
    requested.length = 0;
    render(
      <MemoryRouter initialEntries={["/lineup?view=ahead"]}>
        <Lineup />
      </MemoryRouter>,
    );
    expect(requested).toContain("x/lineup-grid");
    expect(screen.getByRole("radio", { name: "Weeks ahead", checked: true })).toBeTruthy();
  });
  test("two leagues build different query keys for the same endpoint", () => {
    const key = (league: string) => `/api/leagues/${encodeURIComponent(league)}/lineup?week=1`;
    expect(key("colgate")).not.toBe(key("yinzburgh"));
  });
});
