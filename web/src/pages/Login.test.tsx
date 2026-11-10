import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { errorReply, okReply, stubApi } from "@/test/fakeApi";
import Login, { safePath } from "./Login";

const ME = { email: "friend@example.com", is_admin: false, sleeper_user_id: null };

afterEach(() => vi.unstubAllGlobals());

function Landing() {
  const { pathname, search } = useLocation();
  return <p>{`landed on ${pathname}${search}`}</p>;
}

function open(state?: object) {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <Login /> },
      { path: "*", element: <Landing /> },
    ],
    { initialEntries: [{ pathname: "/login", state }] },
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

const signedOut = () => errorReply("unauthorized", "Sign in to continue.", 401);

describe("Login", () => {
  it("has labelled fields a password manager can recognise", async () => {
    stubApi(signedOut);
    open();
    const email = await screen.findByLabelText("Email");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });

  it("signs in and goes to the page the visitor was after", async () => {
    const calls = stubApi((call) => (call.url === "/api/auth/login" ? okReply(ME) : signedOut()));
    open({ from: "/lineup?week=3" });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "friend@example.com");
    await user.type(screen.getByLabelText("Password"), "a long enough password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("landed on /lineup?week=3")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/auth/login")?.body).toEqual({
      email: "friend@example.com",
      password: "a long enough password",
    });
  });

  it("says what went wrong, announces it, clears the password and returns focus to it", async () => {
    stubApi((call) => (call.url === "/api/auth/login" ? errorReply("invalid", "Wrong email or password.", 401) : signedOut()));
    open();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "friend@example.com");
    await user.type(screen.getByLabelText("Password"), "not my password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Password")).toHaveFocus();
    expect(screen.getByLabelText("Email")).toHaveValue("friend@example.com");
  });

  it("disables the button while the request is out, so it cannot be sent twice", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/auth/login") await gate;
        return Response.json(url === "/api/auth/login" ? okReply(ME).body : signedOut().body, {
          status: url === "/api/auth/login" ? 200 : 401,
        });
      }),
    );
    open();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "friend@example.com");
    await user.type(screen.getByLabelText("Password"), "a long enough password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("button", { name: /signing in/i })).toBeDisabled();
    release();
    await waitFor(() => expect(screen.getByText(/landed on/)).toBeInTheDocument());
  });

  it("tells a person whose session ended why they are here", async () => {
    stubApi(signedOut);
    open({ ended: true });
    expect(await screen.findByRole("status")).toHaveTextContent(/session ended/i);
  });

  it("passes a person who is already signed in straight through", async () => {
    stubApi(() => okReply(ME));
    open({ from: "/moves" });
    expect(await screen.findByText("landed on /moves")).toBeInTheDocument();
  });
});

describe("safePath", () => {
  it.each([
    ["/lineup?week=3", "/lineup?week=3"],
    [undefined, "/"],
    ["", "/"],
    ["https://evil.example/", "/"],
    ["//evil.example/", "/"],
    ["javascript:alert(1)", "/"],
  ])("%s -> %s", (from, expected) => {
    expect(safePath(from)).toBe(expected);
  });
});
