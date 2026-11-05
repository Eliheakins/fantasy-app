import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import Moves from "./Moves";

vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [{ league_key: "a", name: "L", current_week: 9 }] } }),
  useLeagueName: () => "L",
}));
vi.mock("@/features/waivers/WaiversView", () => ({ WaiversContent: () => <p>waivers content</p> }));
vi.mock("@/pages/Trades", () => ({ default: () => <p>trades content</p> }));

function Where() {
  return <p data-testid="search">{useLocation().search}</p>;
}

const renderAt = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Moves />
      <Where />
    </MemoryRouter>,
  );

describe("Moves view switch", () => {
  it("defaults to free agents and has one h1", () => {
    renderAt("/moves?league=a");
    expect(screen.getByText("waivers content")).toBeInTheDocument();
    expect(screen.queryByText("trades content")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("?view=trades shows trades", () => {
    renderAt("/moves?view=trades");
    expect(screen.getByText("trades content")).toBeInTheDocument();
    expect(screen.queryByText("waivers content")).toBeNull();
  });

  it("choosing a view writes ?view= and keeps the other params", async () => {
    renderAt("/moves?league=a&week=5");
    await userEvent.click(screen.getByRole("radio", { name: "Trades" }));
    expect(screen.getByText("trades content")).toBeInTheDocument();
    const params = new URLSearchParams(screen.getByTestId("search").textContent ?? "");
    expect(params.get("view")).toBe("trades");
    expect(params.get("week")).toBe("5");
    await userEvent.click(screen.getByRole("radio", { name: "Free agents" }));
    expect(screen.getByText("waivers content")).toBeInTheDocument();
  });

  it("clicking the selected view does not clear it", async () => {
    renderAt("/moves?view=trades");
    await userEvent.click(screen.getByRole("radio", { name: "Trades" }));
    expect(screen.getByText("trades content")).toBeInTheDocument();
  });
});
