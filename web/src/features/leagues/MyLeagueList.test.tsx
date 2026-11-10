import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { LeagueProvider } from "@/lib/league";
import { errorReply, first, okReply, stubScoped } from "@/test/fakeApi";
import { MyLeagueList } from "./MyLeagueList";

afterEach(() => vi.unstubAllGlobals());

const QUEUED = { league_id: "111", league_key: "sl-111", name: "Waiting League", status: "queued", error: null };
const READY = { league_id: "222", league_key: "sl-222", name: "Ready League", status: "ready", error: null };
const BROKEN = { league_id: "333", league_key: "sl-333", name: "Broken League", status: "error", error: "Sleeper refused this league or did not answer." };

function open() {
  const router = createMemoryRouter(
    [
      { path: "/my-leagues", element: <MyLeagueList /> },
      { path: "/", element: <p>home</p> },
    ],
    { initialEntries: ["/my-leagues"] },
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <LeagueProvider>
        <RouterProvider router={router} />
      </LeagueProvider>
    </QueryClientProvider>,
  );
  return router;
}

describe("MyLeagueList", () => {
  it("says so when nothing has been added", async () => {
    stubScoped("/api/me/", () => okReply([]));
    open();
    expect(await screen.findByText("You have not added a league yet.")).toBeInTheDocument();
  });

  it("shows where each league stands in words, not colour", async () => {
    stubScoped("/api/me/", () => okReply([QUEUED, READY, BROKEN]));
    open();
    expect(await screen.findByText("Waiting for the next refresh")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText(/problem: sleeper refused this league/i)).toBeInTheDocument();
  });

  it("offers Open only for a league that is ready, and opens it", async () => {
    stubScoped("/api/me/", () => okReply([QUEUED, READY]));
    const router = open();
    expect(await screen.findByText("Waiting League")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open Waiting League" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open Ready League" }));
    expect(router.state.location.pathname).toBe("/");
    expect(window.localStorage.getItem("fantasy.league")).toBe("sl-222");
  });

  it("asks twice before removing a league", async () => {
    let listed = [QUEUED];
    const calls = stubScoped("/api/me/", (call) => {
      if (call.method === "DELETE") {
        listed = [];
        return okReply({ league_id: "111" });
      }
      return okReply(listed);
    });
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove Waiting League" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm remove Waiting League" }));
    expect(calls.filter((c) => c.method === "DELETE").map((c) => c.url)).toEqual(["/api/me/leagues/111"]);
    expect(await screen.findByText("You have not added a league yet.")).toBeInTheDocument();
  });

  it("lets the person back out of a removal", async () => {
    const calls = stubScoped("/api/me/", () => okReply([QUEUED]));
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove Waiting League" }));
    await user.click(first(screen.getAllByRole("button", { name: "Cancel" })));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(screen.getByRole("button", { name: "Remove Waiting League" })).toBeInTheDocument();
  });

  it("shows why a removal failed", async () => {
    stubScoped("/api/me/", (call) => (call.method === "DELETE" ? errorReply("no_data", "You have not added that league.", 404) : okReply([QUEUED])));
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove Waiting League" }));
    await user.click(screen.getByRole("button", { name: "Confirm remove Waiting League" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You have not added that league.");
  });
});
