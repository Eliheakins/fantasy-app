import { render, screen } from "@testing-library/react";
import { Delta } from "./Delta";

describe("Delta", () => {
  it("a gain carries a plus sign, an up arrow and the better colour", () => {
    render(<Delta points={4.1} />);
    const el = screen.getByText("+4.1 ▲");
    expect(el.className).toContain("text-positive");
  });

  it("a loss carries a minus sign, a down arrow and the worse colour", () => {
    render(<Delta points={-2} />);
    expect(screen.getByText("-2.0 ▼").className).toContain("text-negative");
  });

  it("a change inside the noise band is ~ prefixed and neutral", () => {
    render(<Delta points={0.3} />);
    const el = screen.getByText("~0.3");
    expect(el.className).toContain("text-mark-muted");
  });

  it("takes the noise threshold of its unit", () => {
    render(<Delta points={0.02} noise={0.05} />);
    expect(screen.getByText("~0.02")).toBeInTheDocument();
  });

  it("a toss-up change is never coloured", () => {
    render(<Delta points={3} confidence="toss-up" />);
    expect(screen.getByText("+3.0 ▲").className).toContain("text-mark-muted");
  });
});
