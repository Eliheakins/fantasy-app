import { render, screen } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { Explain, ExplainDelta } from "./Explain";

describe("Explain", () => {
  it("opens on click, shows what drives the number, and Esc closes it and returns focus", async () => {
    const user = userEvent.setup();
    render(<Explain why="Net of the drop.">62%</Explain>);
    const button = screen.getByRole("button", { name: /62%.*what drives this/i });
    await user.click(button);
    expect(screen.getByText("Net of the drop.")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByText("Net of the drop.")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("opens from the keyboard with Enter", async () => {
    const user = userEvent.setup();
    render(<Explain why="Paired draws.">55%</Explain>);
    await user.tab();
    await user.keyboard("{Enter}");
    expect(screen.getByText("Paired draws.")).toBeInTheDocument();
  });

  it("ExplainDelta keeps the delta's sign and arrow as the button label", async () => {
    render(
      <ExplainDelta points={4.1} why="From the stored simulation.">
        {null}
      </ExplainDelta>,
    );
    expect(screen.getByRole("button", { name: /\+4\.1 ▲.*what drives this/i })).toBeInTheDocument();
  });

  it("reports aria-expanded and labels the dialog", async () => {
    const user = userEvent.setup();
    render(<Explain why="Why.">62%</Explain>);
    const button = screen.getByRole("button", { name: /62%/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: "What drives this number" })).toBeInTheDocument();
  });

  it("names what the number is about when asked", () => {
    render(
      <Explain why="Why." about="Flex slot, 64% of paired draws">
        lean
      </Explain>,
    );
    expect(screen.getByRole("button", { name: /lean.*Flex slot, 64% of paired draws.*what drives this/ })).toBeInTheDocument();
  });

  it("returns focus to the trigger on Esc even when the parent re-renders around it", async () => {
    const user = userEvent.setup();
    function Parent() {
      const [n, setN] = useState(0);
      return (
        <div>
          <button onClick={() => setN(n + 1)}>refetch</button>
          <Explain why="Why.">62%</Explain>
        </div>
      );
    }
    render(<Parent />);
    const trigger = screen.getByRole("button", { name: /62%/ });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "refetch" })); // closes it; still mounted
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });
});
