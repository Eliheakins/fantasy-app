import { screen } from "@testing-library/react";
import { okReply, stubApi } from "@/test/fakeApi";
import { NoLeaguesNotice } from "./NoLeaguesNotice";
import { renderWithProviders } from "@/test/render";

function open() {
  renderWithProviders(<NoLeaguesNotice />, { route: "/", league: true });
}

describe("NoLeaguesNotice", () => {
  it("points an account with no leagues to where it can add one", async () => {
    stubApi(({ url }) => (url === "/api/leagues" ? okReply([]) : undefined));
    open();
    expect(await screen.findByText("You have no leagues yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add your Sleeper league" })).toHaveAttribute("href", "/my-leagues");
  });

  it("stays out of the way when there is a league", async () => {
    stubApi(({ url }) => (url === "/api/leagues" ? okReply([{ league_key: "a", name: "A" }]) : undefined));
    open();
    await screen.findByRole("status", {}, { timeout: 200 }).catch(() => null);
    expect(screen.queryByText("You have no leagues yet.")).not.toBeInTheDocument();
  });

  it("says nothing while the league list is still loading", () => {
    stubApi(({ url }) => (url === "/api/leagues" ? okReply([]) : undefined));
    open();
    expect(screen.queryByText("You have no leagues yet.")).not.toBeInTheDocument();
  });
});
