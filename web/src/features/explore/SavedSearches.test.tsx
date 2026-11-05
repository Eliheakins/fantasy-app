import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SavedSearches } from "./SavedSearches";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

const renderAt = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <SavedSearches />
    </MemoryRouter>,
  );

describe("SavedSearches", () => {
  it("saves the current query under a name, lists it as a link that re-runs it, and deletes it", async () => {
    const user = userEvent.setup();
    renderAt("/players/find?league=a&team=2&p=00-1&s=rec_yards");
    await user.type(screen.getByLabelText("Name this search"), "Chase yards");
    await user.click(screen.getByRole("button", { name: "Save search" }));
    const link = screen.getByRole("link", { name: "Chase yards" });
    expect(link).toHaveAttribute("href", "/players/find?p=00-1&s=rec_yards&league=a&team=2");
    expect(JSON.parse(window.localStorage.getItem("fantasy.savedSearches") ?? "[]")).toEqual([{ name: "Chase yards", query: "p=00-1&s=rec_yards" }]);
    await user.click(screen.getByRole("button", { name: "Delete Chase yards" }));
    expect(screen.queryByRole("link", { name: "Chase yards" })).toBeNull();
    expect(window.localStorage.getItem("fantasy.savedSearches")).toBe("[]");
  });

  it("lists searches saved earlier", () => {
    window.localStorage.setItem("fantasy.savedSearches", JSON.stringify([{ name: "Old one", query: "s=x" }]));
    renderAt("/players/find");
    expect(screen.getByRole("link", { name: "Old one" })).toHaveAttribute("href", "/players/find?s=x");
  });

  it("does not save a query with nothing in it", async () => {
    const user = userEvent.setup();
    renderAt("/players/find?league=a");
    await user.type(screen.getByLabelText("Name this search"), "Empty");
    expect(screen.getByRole("button", { name: "Save search" })).toBeDisabled();
  });

  it("still renders and keeps the search for this visit when storage throws, and says it was not kept", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    const user = userEvent.setup();
    renderAt("/players/find?s=rec_yards");
    await user.type(screen.getByLabelText("Name this search"), "Temp");
    await user.click(screen.getByRole("button", { name: "Save search" }));
    expect(screen.getByRole("link", { name: "Temp" })).toBeInTheDocument();
    expect(screen.getByText(/could not be stored/i)).toBeInTheDocument();
  });

  it("renders with a corrupt stored value as an empty list", () => {
    window.localStorage.setItem("fantasy.savedSearches", "{oops");
    renderAt("/players/find?s=x");
    expect(screen.getByText("Saved searches (0)")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Name this search")).toHaveLength(1);
  });

  it("stops at 50 searches and says so", () => {
    window.localStorage.setItem("fantasy.savedSearches", JSON.stringify(Array.from({ length: 50 }, (_, i) => ({ name: `n${i}`, query: "s=x" }))));
    renderAt("/players/find?s=y");
    expect(screen.getByRole("button", { name: "Save search" })).toBeDisabled();
    expect(screen.getByText(/keep 50 searches/)).toBeInTheDocument();
  });
});
