import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { documentTitle, pageTitle, useRouteAnnounce } from "./useRouteAnnounce";

function Shell() {
  useRouteAnnounce(null);
  return (
    <main id="main" tabIndex={-1}>
      <Link to="/lineup">go</Link>
      <Routes>
        <Route path="/lineup" element={<PageHeader title="Lineup" />} />
        <Route path="*" element={<PageHeader title="Home" />} />
      </Routes>
    </main>
  );
}

describe("route titles", () => {
  it("uses the nav title, else not found", () => {
    expect(pageTitle("/lineup")).toBe("Lineup");
    expect(pageTitle("/players")).toBe("Player outlook");
    expect(pageTitle("/nope")).toBe("Page not found");
  });

  it("inserts the viewed team", () => {
    expect(documentTitle("/lineup", "Rival")).toBe("Lineup · Rival · Fantasy");
    expect(documentTitle("/lineup", null)).toBe("Lineup · Fantasy");
  });
});

describe("useRouteAnnounce", () => {
  it("sets the title and focuses the new heading after navigating, but not on first load", async () => {
    render(<MemoryRouter initialEntries={["/"]}><Shell /></MemoryRouter>);
    expect(document.title).toBe("Home · Fantasy");
    expect(screen.getByRole("heading", { name: "Home" })).not.toHaveFocus();
    await userEvent.click(screen.getByText("go"));
    expect(document.title).toBe("Lineup · Fantasy");
    expect(screen.getByRole("heading", { name: "Lineup" })).toHaveFocus();
  });
});
