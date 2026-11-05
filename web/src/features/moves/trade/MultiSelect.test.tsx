import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MultiSelect } from "./MultiSelect";

const OPTIONS = [
  { id: "a", label: "Allen (QB, 300 pts)" },
  { id: "b", label: "Barkley (RB, 200 pts)" },
  { id: "c", label: "Chase (WR, 250 pts)" },
];

function Harness({ max }: { max?: number }) {
  const [sel, setSel] = useState<readonly string[]>([]);
  return <MultiSelect legend="I give" options={OPTIONS} selected={sel} onChange={setSel} max={max} />;
}

describe("MultiSelect", () => {
  it("toggles with the keyboard and shows the count", async () => {
    render(<Harness />);
    const user = userEvent.setup();
    await user.tab();
    await user.tab();
    await user.keyboard(" ");
    expect(screen.getByRole("checkbox", { name: "Allen (QB, 300 pts)" })).toBeChecked();
    expect(screen.getByText(/1 selected/)).toBeInTheDocument();
  });
  it("disables unchecked boxes at the cap", async () => {
    render(<Harness max={1} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Allen/ }));
    expect(screen.getByRole("checkbox", { name: /Barkley/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /Allen/ })).toBeEnabled();
  });
  it("filters by label", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByRole("searchbox", { name: "Filter I give" }), "chase");
    expect(screen.queryByRole("checkbox", { name: /Allen/ })).toBeNull();
    expect(screen.getByRole("checkbox", { name: /Chase/ })).toBeInTheDocument();
  });
});
