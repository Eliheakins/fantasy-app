import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { PlayerLink } from "./PlayerLink";

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}
const renderLink = (ui: React.ReactElement, entry = "/") =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      {ui}
      <Routes><Route path="*" element={<Where />} /></Routes>
    </MemoryRouter>,
  );

describe("PlayerLink", () => {
  it("links to the player page keeping league, team and week only", async () => {
    renderLink(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" />, "/lineup?league=a&team=2&week=5&x=1");
    const link = screen.getByRole("link", { name: "Ja'Marr Chase" });
    expect(link).toHaveAttribute("href", "/players/00-1?league=a&team=2&week=5");
    await userEvent.setup().click(link);
    expect(screen.getByTestId("where")).toHaveTextContent("/players/00-1?league=a&team=2&week=5");
  });
  it("names the player in the stats variant", () => {
    renderLink(<PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" text="stats" />);
    expect(screen.getByRole("link", { name: "stats for Ja'Marr Chase" })).toBeInTheDocument();
  });
  it("is plain text for a DEF or a missing id", () => {
    renderLink(
      <>
        <p><PlayerLink gsisId="00-2" name="Bills" position="DEF" /></p>
        <p><PlayerLink gsisId={null} name="Nobody" position="WR" /></p>
      </>,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Bills")).toBeInTheDocument();
    expect(screen.getByText("Nobody")).toBeInTheDocument();
  });
});
