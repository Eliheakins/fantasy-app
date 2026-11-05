import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { redirectRoutes } from "./redirects";

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

function landing(entry: string): URL {
  const router = createMemoryRouter([...redirectRoutes, { path: "*", element: <Where /> }], { initialEntries: [entry] });
  render(<RouterProvider router={router} />);
  return new URL(screen.getByTestId("where").textContent ?? "", "http://x");
}

const SHARED = "league=a&team=2&week=5";

describe("old paths redirect to the new IA", () => {
  it.each([
    ["/waivers", "/moves", "fa"],
    ["/trades", "/moves", "trades"],
  ])("%s lands on %s with view=%s and league, team, week and other params kept", (from, to, view) => {
    const url = landing(`${from}?${SHARED}&x=1`);
    expect(url.pathname).toBe(to);
    expect(url.searchParams.get("view")).toBe(view);
    expect([...url.searchParams.keys()].sort()).toEqual(["league", "team", "view", "week", "x"]);
    expect(url.searchParams.get("week")).toBe("5");
  });

  it.each([
    ["/outlook", "/season"],
    ["/scoreboard", "/season"],
    ["/league", "/season"],
    ["/digest", "/"],
    ["/scorecard", "/model"],
  ])("%s lands on %s keeping league, team and week", (from, to) => {
    const url = landing(`${from}?${SHARED}`);
    expect(url.pathname).toBe(to);
    expect(url.search).toBe(`?${SHARED}`);
  });

  it("/explore lands on /players/find keeping Explore's own params", () => {
    const url = landing(`/explore?${SHARED}&p=00-0033873&s=rec_yards&s=rec_receptions&by=week`);
    expect(url.pathname).toBe("/players/find");
    expect(url.searchParams.getAll("s")).toEqual(["rec_yards", "rec_receptions"]);
    expect(url.searchParams.get("p")).toBe("00-0033873");
    expect(url.searchParams.get("team")).toBe("2");
  });

  it("a redirect with no query lands with no query", () => {
    expect(landing("/league").search).toBe("");
  });

  it("keeps the hash", () => {
    const router = createMemoryRouter([...redirectRoutes, { path: "*", element: <Where /> }], { initialEntries: ["/league?week=2#luck"] });
    render(<RouterProvider router={router} />);
    expect(router.state.location.hash).toBe("#luck");
  });
});
