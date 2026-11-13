import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { errorReply, first, okReply, stubScoped } from "@/test/fakeApi";
import { MyLeagueList } from "./MyLeagueList";
import { renderWithProviders } from "@/test/render";

const QUEUED = { league_id: "111", league_key: "sl-111", name: "Waiting League", status: "queued", error: null, roster_id: 1 };
const READY = { league_id: "222", league_key: "sl-222", name: "Ready League", status: "ready", error: null, roster_id: 1 };
const BROKEN = {
  league_id: "333",
  league_key: "sl-333",
  name: "Broken League",
  status: "error",
  error: "Sleeper refused this league or did not answer.",
  roster_id: 1,
};
const TEAMS = [
  { roster_id: 1, team_name: "Boss FC", owner_id: "u-boss", owner_name: "Boss" },
  { roster_id: 2, team_name: "Friend FC", owner_id: "u-friend", owner_name: "Friend" },
];

function open() {
  const router = createMemoryRouter(
    [
      { path: "/my-leagues", element: <MyLeagueList /> },
      { path: "/", element: <p>home</p> },
    ],
    { initialEntries: ["/my-leagues"] },
  );
  renderWithProviders(<RouterProvider router={router} />, { league: true });
  return router;
}

describe("MyLeagueList", () => {
  it("says so when nothing has been added", async () => {
    stubScoped("/api/me/leagues", () => okReply([]));
    open();
    expect(await screen.findByText("You have not added a league yet.")).toBeInTheDocument();
  });

  it("shows where each league stands in words, not colour", async () => {
    stubScoped("/api/me/leagues", () => okReply([QUEUED, READY, BROKEN]));
    open();
    expect(await screen.findByText("Waiting for the next refresh")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText(/problem: sleeper refused this league/i)).toBeInTheDocument();
  });

  it("offers Open only for a league that is ready, and opens it", async () => {
    stubScoped("/api/me/leagues", () => okReply([QUEUED, READY]));
    const router = open();
    expect(await screen.findByText("Waiting League")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open Waiting League" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open Ready League" }));
    expect(router.state.location.pathname).toBe("/");
    expect(window.localStorage.getItem("fantasy.league")).toBe("sl-222");
  });

  it("asks twice before removing a league", async () => {
    let listed = [QUEUED];
    const calls = stubScoped("/api/me/leagues", (call) => {
      if (call.method === "DELETE") {
        listed = [];
        return okReply({ league_id: "111" });
      }
      return call.url === "/api/me/leagues" ? okReply(listed) : undefined;
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
    const calls = stubScoped("/api/me/leagues", () => okReply([QUEUED]));
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove Waiting League" }));
    await user.click(first(screen.getAllByRole("button", { name: "Cancel" })));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(screen.getByRole("button", { name: "Remove Waiting League" })).toBeInTheDocument();
  });

  it("shows why a removal failed", async () => {
    stubScoped("/api/me/leagues", (call) =>
      call.method === "DELETE" ? errorReply("no_data", "You have not added that league.", 404) : okReply([QUEUED]),
    );
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove Waiting League" }));
    await user.click(screen.getByRole("button", { name: "Confirm remove Waiting League" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You have not added that league.");
  });

  it("changes which team in a league is yours", async () => {
    let listed = [READY];
    const calls = stubScoped("/api/me/", (call) => {
      if (call.url === "/api/me/sleeper/leagues/222/teams") return okReply(TEAMS);
      if (call.method === "PUT") {
        listed = [{ ...READY, roster_id: 2 }];
        return okReply({ league_id: "222", roster_id: 2 });
      }
      return call.url === "/api/me/leagues" ? okReply(listed) : undefined;
    });
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change your team in Ready League" }));
    const picker = await screen.findByRole("combobox", { name: "Which team in Ready League is yours?" });
    expect(picker).toHaveTextContent("Boss FC (Boss)"); // starts on the team picked before
    await user.click(picker);
    await user.click(await screen.findByRole("option", { name: "Friend FC (Friend)" }));
    await user.click(screen.getByRole("button", { name: "Save team" }));
    expect(await screen.findByRole("button", { name: "Change your team in Ready League" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")).toMatchObject({ url: "/api/me/leagues/222/team", body: { roster_id: 2 } });
  });

  it("asks for a team in a league added before teams were picked", async () => {
    stubScoped("/api/me/", (call) =>
      call.url.endsWith("/teams") ? okReply(TEAMS) : call.url === "/api/me/leagues" ? okReply([{ ...READY, roster_id: null }]) : undefined,
    );
    open();
    expect(await screen.findByText(/no team picked yet/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Pick your team in Ready League" }));
    const picker = await screen.findByRole("combobox", { name: "Which team in Ready League is yours?" });
    expect(picker).toHaveTextContent("Choose your team");
    expect(screen.getByRole("button", { name: "Save team" })).toBeDisabled();
  });

  it("shows why a team change was refused", async () => {
    stubScoped("/api/me/", (call) =>
      call.url.endsWith("/teams")
        ? okReply(TEAMS)
        : call.method === "PUT"
          ? errorReply("invalid", "That team is not in that league.", 409)
          : call.url === "/api/me/leagues"
            ? okReply([READY])
            : undefined,
    );
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change your team in Ready League" }));
    await screen.findByRole("combobox", { name: "Which team in Ready League is yours?" });
    await user.click(screen.getByRole("button", { name: "Save team" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That team is not in that league.");
  });
});
