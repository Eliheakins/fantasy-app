import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LOCAL_EMAIL } from "@/lib/session";
import { okReply, stubApi } from "@/test/fakeApi";
import { Footer } from "./Footer";

afterEach(() => vi.unstubAllGlobals());

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <Footer />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const status = { freshness: [], missing_layers: [], simulation_behind_inputs: null, refresh_runs: [] };

describe("Footer sign-in", () => {
  it("shows who is signed in and signs them out", async () => {
    const calls = stubApi((call) =>
      okReply(call.url === "/api/auth/me" ? { email: "friend@example.com", is_admin: false, sleeper_user_id: null } : status),
    );
    open();
    expect(await screen.findByText("friend@example.com")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/auth/logout")).toBe(true);
  });

  it("offers nothing to sign out of on a run with no accounts", async () => {
    stubApi((call) =>
      okReply(call.url === "/api/auth/me" ? { email: LOCAL_EMAIL, is_admin: true, sleeper_user_id: null } : status),
    );
    open();
    expect(await screen.findByText(/data from sleeper and nflverse/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("links an admin to the admin page and a member to nothing extra", async () => {
    stubApi((call) =>
      okReply(call.url === "/api/auth/me" ? { email: "boss@example.com", is_admin: true, sleeper_user_id: null } : status),
    );
    open();
    expect(await screen.findByRole("link", { name: "Admin" })).toHaveAttribute("href", "/admin");
  });

  it("shows a member no admin link", async () => {
    stubApi((call) =>
      okReply(call.url === "/api/auth/me" ? { email: "friend@example.com", is_admin: false, sleeper_user_id: null } : status),
    );
    open();
    await screen.findByText("friend@example.com");
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });
});
