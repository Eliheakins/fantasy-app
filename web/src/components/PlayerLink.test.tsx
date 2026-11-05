import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { PlayerLink } from "./PlayerLink";

const renderLink = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("PlayerLink", () => {
  it("is a button that opens the stats sheet, not a link", () => {
    renderLink(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByRole("button", { name: "Ja'Marr Chase, open stats" })).toBeInTheDocument();
  });
  it("names the player in the stats variant", () => {
    renderLink(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" text="stats" />);
    expect(screen.getByRole("button", { name: "stats for Ja'Marr Chase, open stats" })).toBeInTheDocument();
  });
  it("is plain text for a DEF", () => {
    renderLink(<PlayerLink gsisId="00-2" name="Bills" position="DEF" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Bills")).toBeInTheDocument();
  });
});
