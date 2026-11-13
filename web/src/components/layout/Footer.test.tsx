import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LOCAL_EMAIL } from "@/lib/session";
import { type Call, okReply, stubApi } from "@/test/fakeApi";
import { Footer } from "./Footer";
import { renderWithProviders } from "@/test/render";

function open() {
  renderWithProviders(<Footer />, { route: "/" });
}

const status = { freshness: [], missing_layers: [], simulation_behind_inputs: null, refresh_runs: [] };

/** The session, the data status and the sign-out routes; anything else is unexpected. */
const answer = (me: object) => (call: Call) =>
  call.url === "/api/auth/me"
    ? okReply(me)
    : call.url === "/api/status"
      ? okReply(status)
      : call.url.startsWith("/api/auth/logout")
        ? okReply({ signed_out: true })
        : undefined;

describe("Footer sign-in", () => {
  it("shows who is signed in and signs them out", async () => {
    const calls = stubApi(answer({ email: "friend@example.com", is_admin: false, sleeper_user_id: null }));
    open();
    expect(await screen.findByText("friend@example.com")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/auth/logout")).toBe(true);
  });

  it("signs out of every device next to the plain sign-out", async () => {
    const calls = stubApi(answer({ email: "friend@example.com", is_admin: false, sleeper_user_id: null }));
    open();
    await screen.findByText("friend@example.com");
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out everywhere" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/auth/logout-everywhere")).toBe(true);
    expect(calls.some((c) => c.url === "/api/auth/logout")).toBe(false);
  });

  it("offers nothing to sign out of on a run with no accounts", async () => {
    stubApi(answer({ email: LOCAL_EMAIL, is_admin: true, sleeper_user_id: null }));
    open();
    expect(await screen.findByText(/data from sleeper and nflverse/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("links an admin to the admin page and a member to nothing extra", async () => {
    stubApi(answer({ email: "boss@example.com", is_admin: true, sleeper_user_id: null }));
    open();
    expect(await screen.findByRole("link", { name: "Admin" })).toHaveAttribute("href", "/admin");
  });

  it("shows a member no admin link", async () => {
    stubApi(answer({ email: "friend@example.com", is_admin: false, sleeper_user_id: null }));
    open();
    await screen.findByText("friend@example.com");
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });
});
