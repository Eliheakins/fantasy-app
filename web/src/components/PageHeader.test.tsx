import { render, screen } from "@testing-library/react";
import { PageHeader } from "./PageHeader";
import { Section } from "./Section";

describe("PageHeader", () => {
  it("renders one focusable h1 with subtitle and actions", () => {
    render(<PageHeader title="Lineup" subtitle="Week 8" actions={<button>Go</button>} />);
    const h1 = screen.getByRole("heading", { level: 1, name: "Lineup" });
    expect(h1).toHaveAttribute("tabindex", "-1");
    expect(screen.getByText("Week 8")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });
});

describe("Section", () => {
  it("labels the region by its h2 and folds the method note", () => {
    render(<Section title="Adds" caption="Best pickups" howCalculated="Method text">body</Section>);
    expect(screen.getByRole("region", { name: "Adds" })).toBeInTheDocument();
    expect(screen.getByText("Best pickups")).toBeInTheDocument();
    expect(screen.getByText("How this is calculated").closest("details")).not.toHaveAttribute("open");
  });

  it("omits the disclosure without a method note", () => {
    render(<Section title="Adds">body</Section>);
    expect(screen.queryByText("How this is calculated")).toBeNull();
  });
});
