import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { UNAUTHORIZED_EVENT } from "@/api/envelope";
import { errorReply, okReply, stubScoped } from "@/test/fakeApi";
import { RequireSession } from "./RequireSession";
import { renderWithProviders } from "@/test/render";

const ME = { email: "friend@example.com", is_admin: false, sleeper_user_id: null };

/** Prints where the gate sent the visitor, and the state it passed along. */
function SignInPage() {
  const { state } = useLocation();
  return <p>{`sign in page ${JSON.stringify(state)}`}</p>;
}

function open(entry = "/lineup?week=3") {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <SignInPage /> },
      { element: <RequireSession />, children: [{ path: "*", element: <p>the private page</p> }] },
    ],
    { initialEntries: [entry] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

describe("RequireSession", () => {
  it("shows the app to a signed-in person", async () => {
    stubScoped("/api/auth/", () => okReply(ME));
    open();
    expect(await screen.findByText("the private page")).toBeInTheDocument();
  });

  it("says it is checking while it waits", () => {
    stubScoped("/api/auth/", () => okReply(ME));
    open();
    expect(screen.getByRole("status")).toHaveTextContent(/checking your sign-in/i);
  });

  it("sends a signed-out visitor to sign in and remembers where they were going", async () => {
    stubScoped("/api/auth/", () => errorReply("unauthorized", "Sign in to continue.", 401));
    const router = open("/lineup?week=3");
    expect(await screen.findByText(/sign in page/)).toHaveTextContent('"from":"/lineup?week=3"');
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.queryByText("the private page")).not.toBeInTheDocument();
  });

  it("offers a retry, not a sign-in page, when the server cannot say who is signed in", async () => {
    let healthy = false;
    stubScoped("/api/auth/", () => (healthy ? okReply(ME) : errorReply("server", "Could not read the accounts", 500)));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not read the accounts");
    healthy = true;
    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText("the private page")).toBeInTheDocument();
  });

  it("sends the person to sign in, with a notice, when a request finds the session gone", async () => {
    let signedIn = true;
    stubScoped("/api/auth/", () => (signedIn ? okReply(ME) : errorReply("unauthorized", "Sign in to continue.", 401)));
    open();
    await screen.findByText("the private page");
    signedIn = false;
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });
    await waitFor(() => expect(screen.getByText(/sign in page/)).toHaveTextContent('"ended":true'));
  });
});
