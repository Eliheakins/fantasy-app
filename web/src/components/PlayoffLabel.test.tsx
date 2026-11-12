import { render, screen } from "@testing-library/react";
import { PlayoffLabel } from "./PlayoffLabel";

describe("PlayoffLabel", () => {
  it("shows the label as plain text", () => {
    render(<PlayoffLabel label="Round 1 of the playoffs" />);
    expect(screen.getByText("Round 1 of the playoffs")).toBeInTheDocument();
  });
  it("renders nothing without a label", () => {
    const { container } = render(<PlayoffLabel label={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
