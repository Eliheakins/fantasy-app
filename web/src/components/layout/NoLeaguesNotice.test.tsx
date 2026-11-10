import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LeagueProvider } from "@/lib/league";
import { okReply, stubApi } from "@/test/fakeApi";
import { NoLeaguesNotice } from "./NoLeaguesNotice";

afterEach(() => vi.unstubAllGlobals());

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <LeagueProvider>
          <NoLeaguesNotice />
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NoLeaguesNotice", () => {
  it("points an account with no leagues to where it can add one", async () => {
    stubApi(() => okReply([]));
    open();
    expect(await screen.findByText("You have no leagues yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add your Sleeper league" })).toHaveAttribute("href", "/my-leagues");
  });

  it("stays out of the way when there is a league", async () => {
    stubApi(() => okReply([{ league_key: "a", name: "A" }]));
    open();
    await screen.findByRole("status", {}, { timeout: 200 }).catch(() => null);
    expect(screen.queryByText("You have no leagues yet.")).not.toBeInTheDocument();
  });

  it("says nothing while the league list is still loading", () => {
    stubApi(() => okReply([]));
    open();
    expect(screen.queryByText("You have no leagues yet.")).not.toBeInTheDocument();
  });
});
