import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LeagueProvider } from "@/lib/league";
import { errorReply, okReply, stubApi, type Reply } from "@/test/fakeApi";
import { WelcomeDialog } from "./WelcomeDialog";

afterEach(() => vi.unstubAllGlobals());

const LEAGUE = { league_key: "a", league_id: "1", name: "Colgate" };
const TITLE = "Welcome. Add your Sleeper leagues";

function open(leagues: unknown[], mine: Reply) {
  const calls = stubApi((call) => (call.url.startsWith("/api/me/leagues") ? mine : okReply(leagues)));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <LeagueProvider>
        <WelcomeDialog />
      </LeagueProvider>
    </QueryClientProvider>,
  );
  return calls;
}

/** Both answers are in, so a dialog that was going to open has had its chance. */
async function settled(calls: { url: string }[]) {
  await waitFor(() => expect(calls.map((c) => c.url).sort()).toEqual(["/api/leagues", "/api/me/leagues"]));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("WelcomeDialog", () => {
  it("asks a new account for its Sleeper username and leagues", async () => {
    open([], okReply([]));
    expect(await screen.findByRole("dialog", { name: TITLE })).toBeInTheDocument();
    expect(screen.getByLabelText("Your Sleeper username")).toBeInTheDocument();
  });

  it("closes when the person is done", async () => {
    open([], okReply([]));
    await userEvent.setup().click(await screen.findByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("stays shut for an account that can already see leagues", async () => {
    await settled(open([LEAGUE], okReply([])));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("stays shut with no account (login off)", async () => {
    await settled(open([], errorReply("unauthorized", "Sign in to add leagues.", 401)));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
