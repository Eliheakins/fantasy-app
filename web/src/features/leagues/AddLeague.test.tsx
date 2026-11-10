import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { errorReply, okReply, stubApi } from "@/test/fakeApi";
import { AddLeague } from "./AddLeague";

afterEach(() => vi.unstubAllGlobals());

const GOOD = { league_id: "111", name: "Friends League", num_teams: 10, added: false, problem: null };
const CHOPPED = { league_id: "444", name: "Chopped", num_teams: 16, added: false, problem: "This league has no playoff bracket." };
const MINE = { league_id: "222", name: "Already Mine", num_teams: 12, added: true, problem: null };
const LOOKUP = { username: "FriendUser", display_name: "Friend", leagues: [GOOD, CHOPPED, MINE] };

function Harness() {
  const [username, setUsername] = useState("");
  return <AddLeague username={username} onUsername={setUsername} />;
}

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Harness />
    </QueryClientProvider>,
  );
}

async function find(name = "FriendUser") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your Sleeper username"), name);
  await user.click(screen.getByRole("button", { name: "Find my leagues" }));
  return user;
}

describe("AddLeague", () => {
  it("says what the username is and is not", () => {
    stubApi(() => okReply(LOOKUP));
    open();
    expect(screen.getByText(/cannot confirm who you are/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Your Sleeper username")).toHaveAttribute("autocomplete", "off");
  });

  it("lists the leagues found, marking the ones already added and the ones that cannot be", async () => {
    const calls = stubApi(() => okReply(LOOKUP));
    open();
    await find();
    expect(await screen.findByText("Leagues for Friend this season")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ url: "/api/me/sleeper/lookup", body: { username: "FriendUser" } });
    expect(screen.getByRole("button", { name: "Add Friends League" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Add Chopped" })).toBeDisabled();
    expect(screen.getByText(/cannot be added: this league has no playoff bracket/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Already Mine" })).not.toBeInTheDocument();
    expect(screen.getByText("Added")).toBeInTheDocument();
  });

  it("explains an unknown username", async () => {
    stubApi(() => errorReply("no_data", "No Sleeper user has that name.", 404));
    open();
    await find("Nobody");
    expect(await screen.findByRole("alert")).toHaveTextContent("No Sleeper user has that name.");
    expect(screen.queryByText(/Leagues for/)).not.toBeInTheDocument();
  });

  it("explains a Sleeper outage", async () => {
    stubApi(() => errorReply("server", "Sleeper did not answer. Try again in a minute.", 502));
    open();
    await find();
    expect(await screen.findByRole("alert")).toHaveTextContent(/sleeper did not answer/i);
  });

  it("says when the user has no leagues this season", async () => {
    stubApi(() => okReply({ ...LOOKUP, leagues: [] }));
    open();
    await find();
    expect(await screen.findByText("No leagues found for this season.")).toBeInTheDocument();
  });

  it("adds a league, says it will be ready after the next refresh, and marks it added", async () => {
    const calls = stubApi((call) =>
      call.url === "/api/me/leagues"
        ? okReply({ league_id: "111", league_key: "sl-111", name: "Friends League", status: "queued", error: null })
        : okReply(LOOKUP),
    );
    open();
    const user = await find();
    await user.click(await screen.findByRole("button", { name: "Add Friends League" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/added friends league.*next refresh/i);
    expect(calls.find((c) => c.url === "/api/me/leagues")?.body).toEqual({ username: "FriendUser", league_id: "111" });
    expect(screen.queryByRole("button", { name: "Add Friends League" })).not.toBeInTheDocument();
  });

  it("shows why an add was refused and leaves the button in place", async () => {
    stubApi((call) =>
      call.url === "/api/me/leagues" ? errorReply("invalid", "You can add up to 2 leagues. Remove one to add another.", 409) : okReply(LOOKUP),
    );
    open();
    const user = await find();
    await user.click(await screen.findByRole("button", { name: "Add Friends League" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/up to 2 leagues/i);
    expect(screen.getByRole("button", { name: "Add Friends League" })).toBeEnabled();
  });
});
