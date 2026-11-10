import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { TeamProvider } from "@/lib/TeamProvider";
import { LeagueProvider } from "@/lib/league";
import { errorReply, first, okReply, stubScoped } from "@/test/fakeApi";
import { People } from "./People";

afterEach(() => vi.unstubAllGlobals());

const BOSS = { id: 1, email: "boss@example.com", is_admin: true, has_password: true, invite_pending: false, created_at: "2026-11-01" };
const FRIEND = { id: 2, email: "friend@example.com", is_admin: false, has_password: true, invite_pending: false, created_at: "2026-11-02" };
const WAITING = { id: 3, email: "waiting@example.com", is_admin: false, has_password: false, invite_pending: true, created_at: "2026-11-03" };

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <LeagueProvider>
          <TeamProvider>
            <People />
          </TeamProvider>
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("People", () => {
  it("lists everyone with their role and status", async () => {
    stubScoped("/api/admin/", () => okReply([BOSS, FRIEND, WAITING]));
    open();
    expect(await screen.findAllByText("boss@example.com")).not.toHaveLength(0);
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Invited, not joined yet").length).toBeGreaterThan(0);
  });

  it("offers no remove or new-link buttons for the admin", async () => {
    stubScoped("/api/admin/", () => okReply([BOSS]));
    open();
    await screen.findAllByText("boss@example.com");
    expect(screen.queryByRole("button", { name: /remove boss/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /new link for boss/i })).not.toBeInTheDocument();
  });

  it("creates an invite, shows the full link once, and refreshes the list", async () => {
    let listed = [BOSS];
    const calls = stubScoped("/api/admin/", (call) => {
      if (call.url === "/api/admin/invites") {
        listed = [BOSS, WAITING];
        return okReply({ email: "waiting@example.com", path: "/invite/abc123", valid_days: 7 });
      }
      return okReply(listed);
    });
    open();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email to invite"), "  waiting@example.com ");
    await user.click(screen.getByRole("button", { name: "Create invite link" }));

    const link = await screen.findByLabelText("Invite link");
    expect(link).toHaveValue(`${window.location.origin}/invite/abc123`);
    expect(screen.getByText(/shown only now/i)).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/admin/invites")?.body).toEqual({ email: "waiting@example.com" });
    expect(await screen.findAllByText("Invited, not joined yet")).not.toHaveLength(0);
    expect(screen.getByLabelText("Email to invite")).toHaveValue("");
  });

  it("copies the link", async () => {
    stubScoped("/api/admin/", (call) =>
      call.url === "/api/admin/invites"
        ? okReply({ email: "waiting@example.com", path: "/invite/abc123", valid_days: 7 })
        : okReply([BOSS]),
    );
    const user = userEvent.setup();
    const copied = vi.spyOn(navigator.clipboard, "writeText");
    open();
    await user.type(await screen.findByLabelText("Email to invite"), "waiting@example.com");
    await user.click(screen.getByRole("button", { name: "Create invite link" }));
    await user.click(await screen.findByRole("button", { name: "Copy link" }));
    expect(copied).toHaveBeenCalledWith(`${window.location.origin}/invite/abc123`);
    expect(await screen.findByText("Copied.")).toBeInTheDocument();
  });

  it("shows the server's reason when an invite is refused", async () => {
    stubScoped("/api/admin/", (call) => (call.url === "/api/admin/invites" ? errorReply("invalid", "That email is not valid.", 422) : okReply([BOSS])));
    open();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email to invite"), "friend@example.com");
    await user.click(screen.getByRole("button", { name: "Create invite link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That email is not valid.");
  });

  it("makes a new link for someone who already has an account", async () => {
    const calls = stubScoped("/api/admin/", (call) =>
      call.url === "/api/admin/invites"
        ? okReply({ email: "friend@example.com", path: "/invite/zzz", valid_days: 7 })
        : okReply([BOSS, FRIEND]),
    );
    open();
    const user = userEvent.setup();
    await user.click(first(await screen.findAllByRole("button", { name: "New link for friend@example.com" })));
    expect(await screen.findByLabelText("Invite link")).toHaveValue(`${window.location.origin}/invite/zzz`);
    expect(calls.find((c) => c.url === "/api/admin/invites")?.body).toEqual({ email: "friend@example.com" });
  });

  it("asks twice before removing, and removes only on the second click", async () => {
    let listed = [BOSS, FRIEND];
    const calls = stubScoped("/api/admin/", (call) => {
      if (call.method === "DELETE") {
        listed = [BOSS];
        return okReply({ email: "friend@example.com" });
      }
      return okReply(listed);
    });
    open();
    const user = userEvent.setup();
    await user.click(first(await screen.findAllByRole("button", { name: "Remove friend@example.com" })));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    await user.click(first(screen.getAllByRole("button", { name: "Confirm remove friend@example.com" })));
    expect(calls.filter((c) => c.method === "DELETE").map((c) => c.url)).toEqual(["/api/admin/accounts/2"]);
    await screen.findAllByText("boss@example.com");
    expect(screen.queryByText("friend@example.com")).not.toBeInTheDocument();
  });

  it("lets the admin back out of a removal", async () => {
    const calls = stubScoped("/api/admin/", () => okReply([BOSS, FRIEND]));
    open();
    const user = userEvent.setup();
    await user.click(first(await screen.findAllByRole("button", { name: "Remove friend@example.com" })));
    await user.click(first(screen.getAllByRole("button", { name: "Cancel" })));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(within(document.body).getAllByRole("button", { name: "Remove friend@example.com" }).length).toBeGreaterThan(0);
  });
});
