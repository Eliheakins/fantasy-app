import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { ApiState } from "@/api/envelope";

let lineupState: ApiState<unknown>;
let currentLeague = "x";
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
    render(<Lineup />);
    expect(screen.getByText("Loading…")).toBeTruthy();
  });
  test("running", () => {
    lineupState = { kind: "running", startedAt: null };
    render(<Lineup />);
    expect(screen.getByRole("status")).toBeTruthy();
  });
  test("no data", () => {
    lineupState = { kind: "no_data", message: "none" };
    render(<Lineup />);
    expect(screen.getByText("none")).toBeTruthy();
  });
  test("ok but empty", () => {
    lineupState = { kind: "ready", data: [] };
    render(<Lineup />);
    expect(screen.getByText(/No projections/)).toBeTruthy();
  });
  test("picking a week requests that week, and the pick stays with its league", async () => {
    lineupState = { kind: "ready", data: [] };
    currentLeague = "x";
    const view = render(<Lineup />);
    await userEvent.selectOptions(screen.getByLabelText("Week"), "5");
    expect(requested).toContain("x/lineup?week=5");
    currentLeague = "y";
    view.rerender(<Lineup />);
    expect(requested.at(-1)).toBe("y/win-probability?week=1");
    expect(screen.getByLabelText("Week")).toHaveValue("1");
    currentLeague = "x";
  });
  test("two leagues build different query keys for the same endpoint", () => {
    const key = (league: string) => `/api/leagues/${encodeURIComponent(league)}/lineup?week=1`;
    expect(key("colgate")).not.toBe(key("yinzburgh"));
  });
});
