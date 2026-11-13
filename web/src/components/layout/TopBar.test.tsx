import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { TopBar } from "./TopBar";
import { okReply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

beforeEach(() => {
  const status = {
    freshness: [],
    missing_layers: [],
    simulation_behind_inputs: null,
    refresh_runs: [],
    live_refresh: { enabled: false, active: false, last_ok_at: null },
  };
  stubApi(({ url }) => (url === "/api/status" ? okReply(status) : url === "/api/leagues" ? okReply([]) : undefined));
  window.localStorage.clear();
});

function renderBar(entry: string) {
  renderWithProviders(
    <>
      <TopBar />
      <Where />
    </>,
    { route: entry, league: true },
  );
}

describe("TopBar Ask box", () => {
  it("opens /ask?q= keeping league, team and week, dropping other page keys", async () => {
    renderBar("/lineup?league=a&team=2&week=3&view=x");

    await userEvent.type(screen.getByRole("textbox", { name: "Ask a question" }), "start Kelce or Kittle{Enter}");

    const where = new URL(screen.getByTestId("where").textContent ?? "", "http://x");
    expect(where.pathname).toBe("/ask");
    expect(where.searchParams.get("q")).toBe("start Kelce or Kittle");
    expect(where.searchParams.get("league")).toBe("a");
    expect(where.searchParams.get("team")).toBe("2");
    expect(where.searchParams.get("week")).toBe("3");
    expect(where.searchParams.has("view")).toBe(false);
  });

  it("does nothing for an empty question", async () => {
    renderBar("/lineup?league=a");

    await userEvent.type(screen.getByRole("textbox", { name: "Ask a question" }), "   {Enter}");

    expect(screen.getByTestId("where").textContent).toBe("/lineup?league=a");
  });

  it("has an Ask icon link to /ask for phones, carrying league, team and week", () => {
    renderBar("/lineup?league=a&team=2&week=3&view=x");

    expect(screen.getByRole("link", { name: "Ask" })).toHaveAttribute("href", "/ask?league=a&team=2&week=3");
  });
});

describe("TopBar week select", () => {
  it("writes ?week= when a week is chosen", async () => {
    renderBar("/lineup?league=a");

    await waitFor(() => expect(screen.getByRole("combobox", { name: "Choose week" })).toBeEnabled());
    await userEvent.click(screen.getByRole("combobox", { name: "Choose week" }));
    await userEvent.click(await screen.findByRole("option", { name: "Week 7" }));

    expect(new URLSearchParams(screen.getByTestId("where").textContent?.split("?")[1]).get("week")).toBe("7");
  });

  it.each(["/lineup", "/season"])("is enabled on %s", async (path) => {
    renderBar(`${path}?league=a`);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Choose week" })).toBeEnabled());
  });

  it.each(["/", "/moves", "/players", "/ask"])("is disabled on %s with a hint that it shows the current week", async (path) => {
    renderBar(`${path}?league=a`);
    const select = screen.getByRole("combobox", { name: "Choose week" });
    expect(select).toBeDisabled();
    expect(select).toHaveAttribute("title", "This page shows the current week");
  });
});
