import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusBanner } from "./StatusBanner";
import { apiKey } from "@/api/useEnvelope";
import { okReply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

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
  renderWithProviders(<StatusBanner />, { route: "/" });
}

const HEALTH = { status: "ok", data_ready: true, data_through: "2026 week 9", built_at: new Date().toISOString(), seasons: [2026] };

const MEMBER = { email: "friend@example.com", is_admin: false, sleeper_user_id: null };

/** Answers /api/stat/health with a plain body and every other route with the envelope; `me` is who is signed in. */
function stubFetch(status: unknown, health: unknown = HEALTH, me: unknown = MEMBER) {
  stubApi(({ url }) =>
    url === "/api/stat/health"
      ? Response.json(health)
      : url === "/api/status"
        ? okReply(status)
        : url === "/api/auth/me"
          ? okReply(me)
          : undefined,
  );
}

beforeEach(() => stubFetch(STATUS));

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

  it.each([
    ["the laptop run", { email: "local", is_admin: true, sleeper_user_id: null }, "make refresh", null],
    ["the server's admin", { email: "admin@example.com", is_admin: true, sleeper_user_id: null }, null, "Refresh from Admin"],
    ["a friend", MEMBER, null, null],
  ])("tells %s how to refresh, and only those who can", async (_who, me, command, link) => {
    stubFetch(STATUS, HEALTH, me);
    renderBanner();
    await screen.findByText(/2 data notices/i);
    if (command) expect(await screen.findByText(command)).toHaveProperty("tagName", "CODE");
    else await waitFor(() => expect(screen.queryByText("make refresh")).toBeNull());
    if (link) expect(await screen.findByRole("link", { name: link })).toHaveAttribute("href", "/admin");
    else expect(screen.queryByRole("link", { name: /Refresh from Admin/ })).toBeNull();
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

  it("keys the stat health like every /api GET, so refreshing the api queries reads it again", async () => {
    const calls = stubApi(({ url }) =>
      url === "/api/stat/health"
        ? Response.json(HEALTH)
        : url === "/api/status"
          ? okReply(STATUS)
          : url === "/api/auth/me"
            ? okReply(MEMBER)
            : undefined,
    );
    const { client } = renderWithProviders(<StatusBanner />, { route: "/" });
    await waitFor(() => expect(client.getQueryData(apiKey("/api/stat/health"))).toEqual(HEALTH));
    await client.invalidateQueries({ queryKey: ["api"] });
    expect(calls.filter((c) => c.url === "/api/stat/health")).toHaveLength(2);
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
    stubApi(({ url }) =>
      url === "/api/stat/health"
        ? new Response("boom", { status: 500 })
        : url === "/api/status"
          ? okReply(STATUS)
          : url === "/api/auth/me"
            ? okReply(MEMBER)
            : undefined,
    );
    renderBanner();
    expect(await screen.findByText(/2 data notices/i)).toBeInTheDocument();
  });

  it("shows the not-built notice even when /api/status fails", async () => {
    stubApi(({ url }) => {
      if (url === "/api/stat/health") return Response.json({ ...HEALTH, data_ready: false, built_at: null });
      throw new Error("status down");
    });
    renderBanner();
    await userEvent.setup().click(await screen.findByRole("button", { name: /details/i }));
    expect(screen.getByText(/Stat data is not built/)).toBeInTheDocument();
  });
});
