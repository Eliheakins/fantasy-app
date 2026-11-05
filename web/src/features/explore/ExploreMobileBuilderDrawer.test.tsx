import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExploreMobileBuilderDrawer } from "./ExploreMobileBuilderDrawer";

vi.mock("@/features/explore/QueryBuilderSidebarBody", () => ({
  QueryBuilderSidebarScroll: () => <p>builder body</p>,
  QueryBuilderSidebarExecuteFooter: ({ onExecute }: { onExecute: () => void }) => (
    <button type="button" onClick={onExecute}>Execute analysis</button>
  ),
}));

describe("ExploreMobileBuilderDrawer", () => {
  it("closes the sheet and runs the query when Execute analysis is pressed", async () => {
    const onExecute = vi.fn();
    render(<ExploreMobileBuilderDrawer sidebarScrollProps={{} as never} running={false} onExecute={onExecute} />);
    await userEvent.click(screen.getByRole("button", { name: "Open query builder" }));
    expect(screen.getByRole("dialog", { name: "Query builder" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Execute analysis" }));

    expect(onExecute).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
