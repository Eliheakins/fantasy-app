import { render, screen } from "@testing-library/react";
import { RangeBar } from "./RangeBar";

describe("RangeBar", () => {
  it("exposes the numbers as an accessible image", () => {
    render(<RangeBar p10={12.1} p50={17.2} p90={23.4} domain={[0, 30]} />);
    expect(screen.getByRole("img", { name: "Median 17.2, range 12.1 to 23.4" })).toBeInTheDocument();
  });
  it("falls back to a tick when an end is missing", () => {
    const { container } = render(<RangeBar p50={17.2} domain={[0, 30]} />);
    expect(container.querySelectorAll("rect")).toHaveLength(1);
    expect(screen.getByRole("img", { name: "Median 17.2, range unavailable" })).toBeInTheDocument();
  });
});
