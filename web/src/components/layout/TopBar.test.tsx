import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { TopBar } from "./TopBar";
import { LeagueProvider } from "@/lib/league";

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

beforeEach(() => {
  const status = { freshness: [], missing_layers: [], simulation_behind_inputs: null, live_refresh: { enabled: false, active: false, last_ok_at: null } };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json({ status: "ok", data: url.startsWith("/api/status") ? status : [], error: null, started_at: null }),
    ),
  );
  window.localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function renderBar(entry: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <LeagueProvider>
          <TopBar />
          <Where />
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TopBar Ask box", () => {
  it("opens /ask?q= keeping league and team, dropping other page keys", async () => {
    renderBar("/lineup?league=a&team=2&week=3");

    await userEvent.type(screen.getByRole("textbox", { name: "Ask a question" }), "start Kelce or Kittle{Enter}");

    const where = new URL(screen.getByTestId("where").textContent ?? "", "http://x");
    expect(where.pathname).toBe("/ask");
    expect(where.searchParams.get("q")).toBe("start Kelce or Kittle");
    expect(where.searchParams.get("league")).toBe("a");
    expect(where.searchParams.get("team")).toBe("2");
    expect(where.searchParams.has("week")).toBe(false);
  });

  it("does nothing for an empty question", async () => {
    renderBar("/lineup?league=a");

    await userEvent.type(screen.getByRole("textbox", { name: "Ask a question" }), "   {Enter}");

    expect(screen.getByTestId("where").textContent).toBe("/lineup?league=a");
  });

  it("has an icon button that shows the input on phones, and the input keeps its label", async () => {
    renderBar("/home");
    const button = screen.getByRole("button", { name: "Show the ask box" });

    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);

    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("textbox", { name: "Ask a question" })).toBeInTheDocument();
  });
});
