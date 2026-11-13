import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ManifestContext } from "@/stat/react/manifest";
import { okReply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";
import { QueryBuilderPanel } from "./QueryBuilderPanel";

vi.mock("@/stat/engine/statQuery", () => ({
  runStatQuery: vi.fn(async () => ({ columns: ["player_id"], rows: [] })),
}));
vi.mock("@/stat/lib/dataSources", () => ({
  seasonSources: () => [{ year: 2025, url: "mem://2025" }],
  playerGameSource: () => null,
  playerIndexSource: () => null,
}));
vi.mock("@/stat/lib/players", () => ({ getPlayersByIds: async () => [] }));

/** No league: the page's only request is the league list. */
const ROUTES: Record<string, ReturnType<typeof okReply>> = { "/api/leagues": okReply([]) };

function Search() {
  return <p data-testid="search">{useLocation().search}</p>;
}
const params = () => new URLSearchParams(screen.getByTestId("search").textContent ?? "");

function renderPanel(route = "/players/find") {
  stubApi((call) => ROUTES[call.url]);
  renderWithProviders(
    <TooltipProvider>
      <ManifestContext.Provider value={{ manifest: null, seasons: [2024, 2025] }}>
        <QueryBuilderPanel />
        <Search />
      </ManifestContext.Provider>
    </TooltipProvider>,
    { route, league: true, team: true },
  );
}

const query = () => screen.getByRole("group", { name: "Query" });

beforeEach(() => {
  localStorage.clear();
});

describe("Find players query bar", () => {
  it("opens a bare page on the default query, shown as chips and in the URL", async () => {
    renderPanel();
    await waitFor(() => expect(params().getAll("s")).toEqual(["rec_tgt"]));
    expect(within(query()).getByRole("button", { name: "Total, per game or per play" })).toHaveTextContent("Per game");
    expect(within(query()).getByRole("button", { name: "Position" })).toHaveTextContent("WR");
    expect(within(query()).getByRole("button", { name: "Seasons" })).toHaveTextContent("2025");
  });

  it("moves along a toggle group with the arrow keys and picks with Enter, writing the URL", async () => {
    const user = userEvent.setup();
    renderPanel("/players/find?s=rec_tgt&g=per_game");
    await user.click(within(query()).getByRole("button", { name: "Total, per game or per play" }));
    const group = await screen.findByRole("radiogroup", { name: "Total, per game or per play" });
    const item = (name: string) => within(group).getByRole("radio", { name });
    // the popover opens on the chosen item, the group's one tab stop
    await waitFor(() => expect(item("Per game")).toHaveFocus());
    await user.keyboard("{ArrowRight}");
    expect(item("Per play")).toHaveFocus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(item("Total")).toHaveFocus();
    expect(params().get("g")).toBe("per_game");
    await user.keyboard("{Enter}");
    expect(item("Total")).toHaveAttribute("aria-checked", "true");
    expect(params().get("g")).toBe("total");
    expect(within(query()).getByRole("button", { name: "Total, per game or per play" })).toHaveTextContent("Total");
  });

  it("chooses a position from the keyboard", async () => {
    const user = userEvent.setup();
    renderPanel("/players/find?s=rec_tgt");
    await user.click(within(query()).getByRole("button", { name: "Position" }));
    const group = await screen.findByRole("radiogroup", { name: "Position" });
    await waitFor(() => expect(within(group).getByRole("radio", { name: "All positions" })).toHaveFocus());
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(within(group).getByRole("radio", { name: "RB" })).toHaveFocus();
    await user.keyboard(" ");
    expect(params().get("pos")).toBe("RB");
    expect(within(query()).getByRole("button", { name: "Position" })).toHaveTextContent("RB");
  });

  it("adds a situation filter as a removable chip, and Escape closes the popover and returns focus to its trigger", async () => {
    const user = userEvent.setup();
    renderPanel("/players/find?s=rec_tgt");
    const trigger = within(query()).getByRole("button", { name: "Add a situation filter" });
    await user.click(trigger);
    const location = await screen.findByRole("group", { name: "Location" });
    await user.click(within(location).getByRole("button", { name: "Home" }));
    expect(within(location).getByRole("button", { name: "Home" })).toHaveAttribute("aria-pressed", "true");
    expect(params().getAll("f")).toContain("loc-home");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("group", { name: "Location" })).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();

    await user.click(within(query()).getByRole("button", { name: "Remove Location: Home" }));
    expect(params().getAll("f")).not.toContain("loc-home");
  });

  it("folds the rarer situations under More situations", async () => {
    const user = userEvent.setup();
    renderPanel("/players/find?s=rec_tgt");
    await user.click(within(query()).getByRole("button", { name: "Add a situation filter" }));
    const more = (await screen.findByText("More situations")).closest("details")!;
    expect(more).not.toHaveAttribute("open");
    await user.click(screen.getByText("More situations"));
    expect(more).toHaveAttribute("open");
    expect(within(more).getByRole("group", { name: "Down" })).toBeVisible();
  });
});
