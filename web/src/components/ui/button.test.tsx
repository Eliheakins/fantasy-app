import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("Button", () => {
  it("defaults to type button so it never submits a form", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toHaveAttribute("type", "button");
  });

  it("lets props override the type", () => {
    render(<Button type="submit">Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toHaveAttribute("type", "submit");
  });
});
