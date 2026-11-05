import { render, screen } from "@testing-library/react";
import { PlayerLink } from "./PlayerLink";

describe("PlayerLink", () => {
  it("links to the stat app in a new tab with a safe rel, named by its text plus a hidden hint", () => {
    render(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" />);
    const a = screen.getByRole("link", { name: "Ja'Marr Chase game log, opens in a new tab" });
    expect(a).toHaveAttribute("href", expect.stringContaining("/explore?p=00-1&"));
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
  });
  it("names the player in the stats variant", () => {
    render(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" text="stats" />);
    expect(screen.getByRole("link", { name: "stats for Ja'Marr Chase, game log, opens in a new tab" })).toBeInTheDocument();
  });
  it("is plain text for a DEF", () => {
    render(<PlayerLink gsisId="00-2" name="Bills" position="DEF" />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Bills")).toBeInTheDocument();
  });
});
