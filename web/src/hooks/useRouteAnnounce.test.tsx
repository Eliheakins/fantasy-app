import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { documentTitle, PageNameContext, pageTitle, usePageName, useRouteAnnounce } from "./useRouteAnnounce";

/** A page that knows its name only once its data loads, as the player page does. */
function NamedPage({ name }: { name: string | null }) {
  usePageName(name);
  return <PageHeader title={name ?? "Player"} />;
}

function Shell({ viewedTeam = null, name = null }: { viewedTeam?: string | null; name?: string | null }) {
  const setPageName = useRouteAnnounce(viewedTeam);
  return (
    <PageNameContext value={setPageName}>
      <main id="main" tabIndex={-1}>
        <Link to="/lineup">go</Link>
        <Routes>
          <Route path="/lineup" element={<PageHeader title="Lineup" />} />
          <Route path="/players/:gsisId" element={<NamedPage name={name} />} />
          <Route path="*" element={<PageHeader title="This week" />} />
        </Routes>
      </main>
    </PageNameContext>
  );
}

describe("route titles", () => {
  it("uses the nav title, else not found", () => {
    expect(pageTitle("/lineup")).toBe("Lineup");
    expect(pageTitle("/players")).toBe("Players");
    expect(pageTitle("/")).toBe("This week");
    expect(pageTitle("/players/find")).toBe("Find players");
    expect(pageTitle("/players/compare")).toBe("Compare players");
    expect(pageTitle("/model")).toBe("Model scorecard");
    expect(pageTitle("/ask")).toBe("Ask");
    expect(pageTitle("/nope")).toBe("Page not found");
  });

  it("names the pattern routes and the pages outside the shell from nav.ts too", () => {
    expect(pageTitle("/players/00-0036900")).toBe("Player");
    expect(pageTitle("/login")).toBe("Sign in");
    expect(pageTitle("/invite/abc123")).toBe("Choose a password");
    expect(pageTitle("/lineup/")).toBe("Lineup");
    expect(pageTitle("/players/00-1/extra")).toBe("Page not found");
  });

  it("inserts the viewed team", () => {
    expect(documentTitle("Lineup", "Rival")).toBe("Lineup · Rival · Fantasy");
    expect(documentTitle("Lineup", null)).toBe("Lineup · Fantasy");
  });
});

describe("useRouteAnnounce", () => {
  it("sets the title and focuses the new heading after navigating, but not on first load", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Shell />
      </MemoryRouter>,
    );
    expect(document.title).toBe("This week · Fantasy");
    expect(screen.getByRole("heading", { name: "This week" })).not.toHaveFocus();
    await userEvent.click(screen.getByText("go"));
    expect(document.title).toBe("Lineup · Fantasy");
    expect(screen.getByRole("heading", { name: "Lineup" })).toHaveFocus();
  });

  it("takes the name a page gives it, and the nav title again once that page is left", async () => {
    render(
      <MemoryRouter initialEntries={["/players/00-1"]}>
        <Shell name="Ja'Marr Chase" viewedTeam="Rival" />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Ja'Marr Chase · Rival · Fantasy");
    await userEvent.click(screen.getByText("go"));
    expect(document.title).toBe("Lineup · Rival · Fantasy");
    expect(screen.getByRole("heading", { name: "Lineup" })).toHaveFocus();
  });

  it("keeps the nav title while the page has no name yet", () => {
    render(
      <MemoryRouter initialEntries={["/players/00-1"]}>
        <Shell />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Player · Fantasy");
  });
});
