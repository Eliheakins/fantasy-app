import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router";
import { TeamBanner } from "@/components/layout/TeamBanner";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { useTeam } from "@/lib/teamContext";
import { stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const team = (roster_id: number, team_name: string, is_me: boolean) => ({
  roster_id,
  team_name,
  is_me,
  wins: 1,
  losses: 0,
  ties: 0,
  points_for: 10,
  record: "1-0",
});
const routes: Record<string, object> = {
  "/api/leagues": ok([{ league_key: "a", name: "A" }]),
  "/api/leagues/a/teams": ok([team(1, "Mine", true), team(2, "Rival", false)]),
  "/api/leagues/a/roster": ok([]),
};

function mockFetch(): string[] {
  const urls: string[] = [];
  stubApi((call) => {
    urls.push(call.url);
    const body = routes[call.url.split("?")[0] ?? call.url];
    return body === undefined ? undefined : { body };
  });
  return urls;
}

function Probe() {
  useEnvelopeQuery("/api/leagues/{league}/roster", { path: { league: "a" } });
  const { setTeam } = useTeam();
  const { search } = useLocation();
  return (
    <>
      <p data-testid="search">{search}</p>
      <button type="button" onClick={() => setTeam(2)}>
        pick
      </button>
      <button type="button" onClick={() => setTeam(null)}>
        reset
      </button>
    </>
  );
}

function renderAt(entry: string) {
  renderWithProviders(
    <>
      <TeamBanner />
      <Probe />
    </>,
    { route: entry, league: true, team: true },
  );
}

describe("TeamProvider", () => {
  it("sends no team and shows no banner by default", async () => {
    const urls = mockFetch();
    renderAt("/");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster"));
    expect(urls.some((u) => u.includes("team="))).toBe(false);
    expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument();
  });

  it("reads ?team= from the URL, sends it, and shows the banner", async () => {
    const urls = mockFetch();
    renderAt("/?team=2&league=a");
    await screen.findByText("Viewing as Rival");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster?team=2"));
    expect(urls).not.toContain("/api/leagues/a/teams?team=2");
  });

  it("treats my own roster id as the default", async () => {
    const urls = mockFetch();
    renderAt("/?team=1&league=a");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster"));
    expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument();
  });

  it("ignores a team that is not in the league", async () => {
    const urls = mockFetch();
    renderAt("/?team=99&league=a");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/teams"));
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster"));
    expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument();
  });

  it("tells the user and cleans the URL when the linked team is not in the league", async () => {
    mockFetch();
    renderAt("/?team=99&league=a");
    expect(await screen.findByText("That team is not in this league. Showing your team.")).toBeInTheDocument();
    expect(screen.getByTestId("search")).toHaveTextContent("?league=a");
    expect(screen.getByTestId("search")).not.toHaveTextContent("team=");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/not in this league/)).not.toBeInTheDocument();
  });

  it("cleans my own roster id from the URL without a notice", async () => {
    mockFetch();
    renderAt("/?team=1&league=a");
    await waitFor(() => expect(screen.getByTestId("search")).not.toHaveTextContent("team="));
    expect(screen.queryByText(/not in this league/)).not.toBeInTheDocument();
  });

  it("writes the choice to the URL and clears it again", async () => {
    mockFetch();
    renderAt("/");
    await screen.findByText("pick");
    await userEvent.click(screen.getByText("pick"));
    expect(screen.getByTestId("search")).toHaveTextContent("?team=2&league=a");
    await userEvent.click(screen.getByText("reset"));
    expect(screen.getByTestId("search")).toHaveTextContent("");
  });

  it("back to my team clears the banner", async () => {
    mockFetch();
    renderAt("/?team=2&league=a");
    await userEvent.click(await screen.findByText("Back to my team"));
    await waitFor(() => expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument());
  });
});
