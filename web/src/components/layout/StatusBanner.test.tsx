import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusBanner } from "./StatusBanner";

const STATUS = {
  freshness: [{ source: "Sleeper", age_hours: 60, updated_at: "2026-11-01T00:00:00Z" }],
  missing_layers: ["odds"],
  simulation_behind_inputs: null,
  live_refresh: { enabled: false, active: false, last_ok_at: null },
};

function mockMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
}

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><StatusBanner /></QueryClientProvider>);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ status: "ok", data: STATUS, error: null, started_at: null })));
});
afterEach(() => vi.unstubAllGlobals());

describe("StatusBanner", () => {
  it("on a phone, collapses the notices into one line with a disclosure", async () => {
    mockMedia(false);
    renderBanner();
    const toggle = await screen.findByRole("button", { name: /2 data notices/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Stale data/)).toBeNull();
    await userEvent.setup().click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Stale data/)).toBeInTheDocument();
    expect(screen.getByText(/Running without/)).toBeInTheDocument();
  });

  it("on desktop, keeps every notice visible", async () => {
    mockMedia(true);
    renderBanner();
    expect(await screen.findByText(/Stale data/)).toBeInTheDocument();
    expect(screen.getByText(/Running without/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
