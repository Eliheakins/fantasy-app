import { type RenderResult, render as rtlRender, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiState } from "@/api/envelope";
import { WaiversView } from "./WaiversView";

/** Player names link to Explore, which needs a router. */
const render = (ui: ReactElement): RenderResult => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

const ready = <T,>(data: T): ApiState<T> => ({ kind: "ready", data });
const add = {
  gsis_id: "g1",
  full_name: "Jane Doe",
  position: "WR",
  drop_name: "Bob Low",
  delta_points: 12.34,
  playoff_delta: 0.05,
  title_delta: 0.004,
  se_title: 0.005,
  trending_adds: 900,
};
const base = {
  adds: ready([add]),
  def: ready([{ unit: "DEF", name: "Jets", team: "NYJ", is_mine: true, this_week: 8, next_three: 20 }]),
  kickers: { kind: "no_data", message: "x" } as ApiState<never[]>,
  weeks: { kind: "loading" } as ApiState<never[]>,
  selected: null,
  onSelect: () => {},
};

describe("WaiversView", () => {
  it("shows adds with a grey ~ for a title change inside the error", () => {
    render(<WaiversView {...base} />);
    expect(screen.getAllByText("~0.4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+5.0 ▲").length).toBeGreaterThan(0);
    expect(screen.getByText("Run the streaming stage to see this.")).toBeInTheDocument();
  });
  it("links the name to the player page", () => {
    render(<WaiversView {...base} />);
    expect(screen.getAllByRole("link", { name: "Jane Doe" })[0]).toHaveAttribute("href", "/players/g1");
  });
  it("selects a row", async () => {
    const onSelect = vi.fn();
    render(<WaiversView {...base} onSelect={onSelect} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Details for Jane Doe" })[0]!);
    expect(onSelect).toHaveBeenCalledWith("g1");
  });
  it("shows the chart data table for a selected row", () => {
    render(<WaiversView {...base} selected="g1" weeks={ready([{ week: 8, projection: 11.2 }])} />);
    expect(screen.getByText("Jane Doe: next four weeks")).toBeInTheDocument();
    expect(screen.getByText("11.2")).toBeInTheDocument();
  });
  it("renders empty, running and missing-stage states", () => {
    render(<WaiversView {...base} adds={ready([])} />);
    expect(screen.getByText("No free agent adds expected points for your team.")).toBeInTheDocument();
  });
  it("shows elapsed time while the job runs", () => {
    render(<WaiversView {...base} adds={{ kind: "running", startedAt: new Date().toISOString() }} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Working/);
  });

  it("links to the league in Sleeper only when the id is known", () => {
    const { unmount } = render(<WaiversView {...base} sleeperLeagueId="42" />);
    expect(screen.getByRole("link", { name: /Open league in Sleeper/ })).toHaveAttribute("href", "https://sleeper.com/leagues/42");
    unmount();
    render(<WaiversView {...base} />);
    expect(screen.queryByRole("link", { name: /Sleeper/ })).toBeNull();
  });
});
