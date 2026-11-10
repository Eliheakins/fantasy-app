import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusBanner } from "./StatusBanner";

const STATUS = {
  freshness: [{ source: "Sleeper", age_hours: 60, updated_at: "2026-11-01T00:00:00Z" }],
  missing_layers: ["odds"],
  simulation_behind_inputs: null,
  refresh_runs: [],
  live_refresh: { enabled: false, active: false, last_ok_at: null },
};

function mockMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
}

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StatusBanner />
    </QueryClientProvider>,
  );
}

const HEALTH = { status: "ok", data_ready: true, data_through: "2026 week 9", built_at: new Date().toISOString(), seasons: [2026] };

/** Answers /api/stat/health with a plain body and every other route with the envelope. */
function stubFetch(status: unknown, health: unknown = HEALTH) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      String(url).includes("/api/stat/health")
        ? Response.json(health)
        : Response.json({ status: "ok", data: status, error: null, started_at: null }),
    ),
  );
}

beforeEach(() => stubFetch(STATUS));
afterEach(() => vi.unstubAllGlobals());

describe("StatusBanner", () => {
  it.each([
    [false, "phone"],
    [true, "desktop"],
  ])("collapses the notices into one amber line with a details disclosure (%s)", async (wide) => {
    mockMedia(wide);
    renderBanner();
    const toggle = await screen.findByRole("button", { name: /details/i });
    expect(screen.getByText(/2 data notices/i)).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Stale data/)).toBeNull();
    await userEvent.setup().click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Stale data/)).toBeInTheDocument();
    expect(screen.getByText(/Running without/)).toBeInTheDocument();
  });

  it("lists a failed refresh step in the details", async () => {
    stubFetch({
      ...STATUS,
      freshness: [],
      missing_layers: [],
      refresh_runs: [{ stage: "digest", finished_at: "2026-11-05T06:00:00+00:00", status: "failed", error: "boom" }],
    });
    renderBanner();
    await userEvent.setup().click(await screen.findByRole("button", { name: /details/i }));
    expect(screen.getByText(/Refresh step digest failed: boom/)).toBeInTheDocument();
  });

  it("shows nothing when the data is fresh", async () => {
    stubFetch({ ...STATUS, freshness: [], missing_layers: [] });
    renderBanner();
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("adds stale stat data from /api/stat/health to the notices", async () => {
    const built = new Date(Date.now() - 100 * 3_600_000).toISOString();
    stubFetch({ ...STATUS, freshness: [], missing_layers: [] }, { ...HEALTH, built_at: built });
    renderBanner();
    await userEvent.setup().click(await screen.findByRole("button", { name: /details/i }));
    expect(screen.getByText(/Stale data: Stat data \(100 hours old\)/)).toBeInTheDocument();
  });

  it("keeps the /api/status notices when the health call fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stat/health")) return new Response("boom", { status: 500 });
        return Response.json({ status: "ok", data: STATUS, error: null, started_at: null });
      }),
    );
    renderBanner();
    expect(await screen.findByText(/2 data notices/i)).toBeInTheDocument();
  });

  it("shows the not-built notice even when /api/status fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stat/health")) return Response.json({ ...HEALTH, data_ready: false, built_at: null });
        throw new Error("status down");
      }),
    );
    renderBanner();
    await userEvent.setup().click(await screen.findByRole("button", { name: /details/i }));
    expect(screen.getByText(/Stat data is not built/)).toBeInTheDocument();
  });
});
