import { render, screen } from "@testing-library/react";
import { Confidence } from "./Confidence";

describe("Confidence", () => {
  it.each([
    [0.7, "clear"],
    [0.9, "clear"],
    [0.6999, "lean"],
    [0.55, "lean"],
    [0.5499, "toss-up"],
    [0.5, "toss-up"],
    [0, "toss-up"],
  ])("a share of %s reads %s", (share, word) => {
    render(<Confidence share={share} />);
    expect(screen.getByText(word)).toBeInTheDocument();
  });

  it("takes a level directly", () => {
    render(<Confidence level="lean" />);
    expect(screen.getByText("lean")).toBeInTheDocument();
  });
});
