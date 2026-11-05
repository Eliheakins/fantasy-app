import { render, screen } from "@testing-library/react";
import { WinBar } from "./WinBar";

describe("WinBar", () => {
  it("fills my row Forest and every other row light grey when a tone is given", () => {
    render(<><WinBar fraction={0.6} tone="mine" /><WinBar fraction={0.4} tone="other" /><WinBar fraction={0.5} /></>);
    const [mine, other, plain] = screen.getAllByRole("img").map((svg) => svg.querySelectorAll("rect")[1]!.getAttribute("class"));
    expect(mine).toContain("fill-forest");
    expect(other).toContain("fill-chart-other");
    expect(plain).toContain("fill-faint");
    expect(screen.getByText("60%")).toBeInTheDocument();
  });
});
