import { screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { okReply, stubScoped } from "@/test/fakeApi";
import { RequireAdmin } from "./RequireAdmin";
import { renderWithProviders } from "@/test/render";

function open() {
  const router = createMemoryRouter(
    [
      { path: "/", element: <p>home</p> },
      { element: <RequireAdmin />, children: [{ path: "/admin", element: <p>admin page</p> }] },
    ],
    { initialEntries: ["/admin"] },
  );
  renderWithProviders(<RouterProvider router={router} />);
}

describe("RequireAdmin", () => {
  it("opens the page for the admin", async () => {
    stubScoped("/api/auth/", () => okReply({ email: "boss@example.com", is_admin: true, sleeper_user_id: null }));
    open();
    expect(await screen.findByText("admin page")).toBeInTheDocument();
  });

  it("sends a member home", async () => {
    stubScoped("/api/auth/", () => okReply({ email: "friend@example.com", is_admin: false, sleeper_user_id: null }));
    open();
    expect(await screen.findByText("home")).toBeInTheDocument();
    expect(screen.queryByText("admin page")).not.toBeInTheDocument();
  });
});
