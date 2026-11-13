import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { errorReply, okReply, stubScoped } from "@/test/fakeApi";
import RedeemInvite from "./RedeemInvite";
import { renderWithProviders } from "@/test/render";

const ME = { email: "friend@example.com", is_admin: false, sleeper_user_id: null };
const TOKEN = "invite-token-with-enough-length";
const GOOD = "a long enough password";

function open() {
  const router = createMemoryRouter(
    [
      { path: "/invite/:token", element: <RedeemInvite /> },
      { path: "*", element: <p>the app</p> },
    ],
    { initialEntries: [`/invite/${TOKEN}`] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

async function fill(password: string, again: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("New password"), password);
  await user.type(screen.getByLabelText("Type it again"), again);
  await user.click(screen.getByRole("button", { name: /save password/i }));
}

describe("RedeemInvite", () => {
  it("asks for a new password with the autocomplete hints a password manager needs", () => {
    stubScoped("/api/auth/", () => okReply(ME));
    open();
    expect(screen.getByRole("heading", { level: 1, name: "Choose a password" })).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Type it again")).toHaveAttribute("autocomplete", "new-password");
  });

  it("refuses a short password without calling the server", async () => {
    const calls = stubScoped("/api/auth/", () => okReply(ME));
    open();
    await fill("short", "short");
    expect(await screen.findByRole("alert")).toHaveTextContent("Use at least 12 characters.");
    expect(calls).toEqual([]);
    expect(screen.getByLabelText("New password")).toHaveFocus();
    expect(screen.getByLabelText("New password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("New password")).toHaveAccessibleDescription("Use at least 12 characters.");
    expect(screen.getByLabelText("Type it again")).not.toHaveAttribute("aria-invalid");
  });

  it("refuses two different passwords without calling the server, on the second field", async () => {
    const calls = stubScoped("/api/auth/", () => okReply(ME));
    open();
    await fill(GOOD, `${GOOD}!`);
    expect(await screen.findByRole("alert")).toHaveTextContent("not the same");
    expect(calls).toEqual([]);
    expect(screen.getByLabelText("Type it again")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Type it again")).toHaveAccessibleDescription("The two passwords are not the same.");
    expect(screen.getByLabelText("Type it again")).toHaveFocus();
    expect(screen.getByLabelText("New password")).not.toHaveAttribute("aria-invalid");
  });

  it("sends the token from the link with the password, then opens the app", async () => {
    const calls = stubScoped("/api/auth/", () => okReply(ME));
    open();
    await fill(GOOD, GOOD);
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(calls).toEqual([{ url: "/api/auth/redeem", method: "POST", body: { token: TOKEN, password: GOOD } }]);
  });

  it("replaces the invite address after signing in, so the token leaves the history", async () => {
    stubScoped("/api/auth/", () => okReply(ME));
    const router = open();
    await fill(GOOD, GOOD);
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(router.state.historyAction).toBe("REPLACE");
    expect(router.state.location.pathname).toBe("/");
  });

  it("shows why a used or expired link failed and stays on the page", async () => {
    stubScoped("/api/auth/", () => errorReply("invalid", "This invite link was already used.", 400));
    open();
    await fill(GOOD, GOOD);
    expect(await screen.findByRole("alert")).toHaveTextContent("This invite link was already used.");
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
    expect(screen.getByLabelText("New password")).not.toHaveAttribute("aria-invalid");
  });
});
