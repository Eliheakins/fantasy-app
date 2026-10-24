import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { RadioGroup } from "./RadioGroup";

const OPTIONS = [{ key: "a", label: "A" }, { key: "b", label: "B" }, { key: "c", label: "C" }] as const;

function Harness() {
  const [v, setV] = useState<"a" | "b" | "c">("a");
  return <RadioGroup label="Pick" options={OPTIONS} value={v} onChange={setV} />;
}

describe("RadioGroup", () => {
  it("arrow keys move and wrap the selection, with a roving tab stop", async () => {
    render(<Harness />);
    const radio = (n: string) => screen.getByRole("radio", { name: n });
    expect(radio("B")).toHaveAttribute("tabindex", "-1");
    radio("A").focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(radio("B")).toBeChecked();
    expect(radio("B")).toHaveFocus();
    expect(radio("B")).toHaveAttribute("tabindex", "0");
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(radio("C")).toBeChecked();
  });
});
