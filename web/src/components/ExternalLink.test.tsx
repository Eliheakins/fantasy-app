import { render, screen } from "@testing-library/react";
import { ExternalLink } from "./ExternalLink";

describe("ExternalLink", () => {
  it("opens in a new tab safely and says so to screen readers", () => {
    render(<ExternalLink href="https://sleeper.com/leagues/1">Open in Sleeper</ExternalLink>);
    const a = screen.getByRole("link", { name: /Open in Sleeper/ });
    expect(a).toHaveAttribute("href", "https://sleeper.com/leagues/1");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
    expect(a).toHaveAccessibleName(/Open in Sleeper\s*\(opens in a new tab\)/);
    expect(a.querySelector(".sr-only")).toHaveTextContent("(opens in a new tab)");
  });
});
