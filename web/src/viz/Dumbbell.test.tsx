import { render, screen } from "@testing-library/react";
import { Dumbbell } from "./Dumbbell";
import { Sparkline } from "./Sparkline";

describe("Dumbbell", () => {
  it("labels percent values with %", () => {
    render(<Dumbbell before={14} after={19} domain={[0, 30]} measure="Title odds" percent />);
    expect(screen.getByRole("img", { name: "Title odds: 14.0% before, 19.0% after" })).toBeInTheDocument();
  });
  it("uses a tight noise band for percentage points and wins", () => {
    const { rerender } = render(<Dumbbell before={14} after={14.3} domain={[0, 30]} measure="Odds" percent />);
    expect(screen.getByText("+0.3 ▲")).toBeInTheDocument();
    rerender(<Dumbbell before={5} after={5.07} domain={[0, 10]} measure="Wins" />);
    expect(screen.getByText("+0.07 ▲")).toBeInTheDocument();
    rerender(<Dumbbell before={5} after={5.03} domain={[0, 10]} measure="Wins" />);
    expect(screen.getByText("~0.03")).toBeInTheDocument();
  });
  it("falls back to text when a value is not finite", () => {
    const { container } = render(<Dumbbell before={Number.NaN} after={19} domain={[0, 30]} measure="Odds" />);
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByText("Odds: – before, 19.0 after")).toBeInTheDocument();
  });
});

describe("Sparkline", () => {
  it("drops non-finite values", () => {
    const { container } = render(<Sparkline values={[1, Number.NaN, 3, Number.POSITIVE_INFINITY]} />);
    expect(screen.getByRole("img", { name: "Form: 1.0, 3.0" })).toBeInTheDocument();
    expect(container.querySelector("polyline")?.getAttribute("points")).not.toMatch(/NaN|Infinity/);
  });
  it("shows a dash when fewer than two finite values remain", () => {
    render(<Sparkline values={[Number.NaN, 2]} />);
    expect(screen.getByText("–")).toBeInTheDocument();
  });
});
