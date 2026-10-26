import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiState } from "@/api/envelope";
import { WaiversView } from "./WaiversView";

const ready = <T,>(data: T): ApiState<T> => ({ kind: "ready", data });
const add = {
  gsis_id: "g1", full_name: "Jane Doe", position: "WR", drop_name: "Bob Low",
  delta_points: 12.34, playoff_delta: 0.05, title_delta: 0.004, se_title: 0.005, trending_adds: 900,
};
const base = {
  adds: ready([add]),
  strength: ready([{ position: "QB", vor_per_week: 3.2, rank: 2, teams: 12 }]),
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
    expect(screen.getByText(/rank 2 of 12/)).toBeInTheDocument();
  });
  it("selects a row", async () => {
    const onSelect = vi.fn();
    render(<WaiversView {...base} onSelect={onSelect} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Jane Doe" })[0]!);
    expect(onSelect).toHaveBeenCalledWith("g1");
  });
  it("shows the chart data table for a selected row", () => {
    render(
      <WaiversView {...base} selected="g1" weeks={ready([{ week: 8, projection: 11.2 }])} />,
    );
    expect(screen.getByText("Jane Doe: next four weeks")).toBeInTheDocument();
    expect(screen.getByText("11.2")).toBeInTheDocument();
  });
  it("renders empty, running and missing-stage states", () => {
    render(
      <WaiversView
        {...base}
        adds={ready([])}
        strength={{ kind: "no_data", message: "Nothing here" }}
      />,
    );
    expect(screen.getByText("No free agent adds expected points for your team.")).toBeInTheDocument();
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
  it("shows elapsed time while the job runs", () => {
    render(<WaiversView {...base} adds={{ kind: "running", startedAt: new Date().toISOString() }} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Working/);
  });
});
