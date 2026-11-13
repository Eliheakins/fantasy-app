import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { FindPlayersCta, PlayersNav } from "./PlayersNav";

const at = (entry: string) => {
  const { pathname, search } = new URL(entry, "http://localhost");
  render(
    <MemoryRouter initialEntries={[entry]}>
      <PlayersNav here={{ pathname, search }} />
      <FindPlayersCta here={{ pathname, search }} />
    </MemoryRouter>,
  );
};

describe("Players secondary nav", () => {
  it("offers Your players and Find players as tabs, keeping league, team and week", () => {
    at("/players?league=a&team=2&week=3&view=x");
    const nav = screen.getByRole("navigation", { name: "Players" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your players" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Find players" })).toHaveAttribute("href", "/players/find?league=a&team=2&week=3");
  });

  it("marks Find players as current on the finder", () => {
    at("/players/find?league=a");
    expect(screen.getByRole("link", { name: "Find players" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Your players" })).not.toHaveAttribute("aria-current");
  });

  it("has a call to action to find players by any stat", () => {
    at("/players?league=a");
    expect(screen.getByRole("link", { name: /Find players by any stat/ })).toHaveAttribute("href", "/players/find?league=a");
  });
});
