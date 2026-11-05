import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { PlayerLink } from "./PlayerLink";

const renderLink = (ui: React.ReactElement, entry = "/lineup?league=a&team=2&x=1") =>
  render(<MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter>);

describe("PlayerLink", () => {
  it("links to the in-app Explore game log in the same tab, keeping league and team", () => {
    renderLink(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" />);
    const a = screen.getByRole("link", { name: "Ja'Marr Chase game log" });
    const href = new URL(a.getAttribute("href") ?? "", "http://x");
    expect(href.pathname).toBe("/explore");
    expect(href.searchParams.get("p")).toBe("00-1");
    expect(href.searchParams.get("league")).toBe("a");
    expect(href.searchParams.get("team")).toBe("2");
    expect(href.searchParams.has("x")).toBe(false);
    expect(a).not.toHaveAttribute("target");
  });
  it("names the player in the stats variant", () => {
    renderLink(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" text="stats" />);
    expect(screen.getByRole("link", { name: "stats for Ja'Marr Chase, game log" })).toBeInTheDocument();
  });
  it("is plain text for a DEF", () => {
    renderLink(<PlayerLink gsisId="00-2" name="Bills" position="DEF" />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Bills")).toBeInTheDocument();
  });
});
