import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LeagueProvider } from "@/lib/league";
import { TeamProvider } from "@/lib/TeamProvider";
import { errorReply, okReply, stubScoped } from "@/test/fakeApi";
import { RefreshPanel } from "./RefreshPanel";

afterEach(() => vi.unstubAllGlobals());

const RUN = { run_id: "20261109T120000Z", finished_at: "2026-11-09T12:02:00+00:00", stages: 21, failed: 0, seconds: 118 };

function overview(over: object = {}) {
  return { state: "idle", queued: 0, last_finished_at: RUN.finished_at, last_run_failed: false, runs: [RUN], ...over };
}

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <LeagueProvider>
          <TeamProvider>
            <RefreshPanel />
          </TeamProvider>
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RefreshPanel", () => {
  it("says nothing is waiting, how the last run went, and lists recent runs", async () => {
    stubScoped("/api/admin/", () => okReply(overview()));
    open();
    expect(await screen.findByText("No refresh is waiting.")).toBeInTheDocument();
    expect(screen.getByText(/every stage succeeded/i)).toBeInTheDocument();
    expect(screen.getAllByText("20261109T120000Z").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Refresh now" })).toBeEnabled();
  });

  it("warns when the last run had a failed or skipped stage", async () => {
    stubScoped("/api/admin/", () => okReply(overview({ last_run_failed: true })));
    open();
    expect(await screen.findByText(/at least one stage failed or was skipped/i)).toBeInTheDocument();
  });

  it.each([
    ["queued", "A refresh is waiting to start (2 requests).", { queued: 2 }],
    ["queued", "A refresh is waiting to start (1 request).", { queued: 1 }],
    ["running", "A refresh is running.", {}],
  ])("shows the %s state and disables the button", async (state, sentence, extra) => {
    stubScoped("/api/admin/", () => okReply(overview({ state, ...extra })));
    open();
    expect(await screen.findByText(sentence)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh now" })).toBeDisabled();
  });

  it("queues a refresh when the button is pressed", async () => {
    let state = "idle";
    const calls = stubScoped("/api/admin/", (call) => {
      if (call.method === "POST") {
        state = "queued";
        return okReply({ state: "queued", queued: 1, last_finished_at: null, last_run_failed: null });
      }
      return okReply(overview({ state, queued: state === "queued" ? 1 : 0 }));
    });
    open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Refresh now" }));
    expect(await screen.findByText(/waiting to start/i)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST").map((c) => c.url)).toEqual(["/api/admin/refresh"]);
  });

  it("shows why a refresh request failed", async () => {
    stubScoped("/api/admin/", (call) =>
      call.method === "POST" ? errorReply("server", "Could not write the request", 500) : okReply(overview()),
    );
    open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Refresh now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not write the request");
  });
});
