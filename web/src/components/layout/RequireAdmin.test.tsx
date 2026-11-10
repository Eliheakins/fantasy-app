import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { okReply, stubApi } from "@/test/fakeApi";
import { RequireAdmin } from "./RequireAdmin";

afterEach(() => vi.unstubAllGlobals());

function open() {
  const router = createMemoryRouter(
    [
      { path: "/", element: <p>home</p> },
      { element: <RequireAdmin />, children: [{ path: "/admin", element: <p>admin page</p> }] },
    ],
    { initialEntries: ["/admin"] },
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("RequireAdmin", () => {
  it("opens the page for the admin", async () => {
    stubApi(() => okReply({ email: "boss@example.com", is_admin: true, sleeper_user_id: null }));
    open();
    expect(await screen.findByText("admin page")).toBeInTheDocument();
  });

  it("sends a member home", async () => {
    stubApi(() => okReply({ email: "friend@example.com", is_admin: false, sleeper_user_id: null }));
    open();
    expect(await screen.findByText("home")).toBeInTheDocument();
    expect(screen.queryByText("admin page")).not.toBeInTheDocument();
  });
});
