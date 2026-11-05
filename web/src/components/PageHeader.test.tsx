import userEvent from "@testing-library/user-event";
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

describe("PageHeader eyebrow and answer", () => {
  it("shows the eyebrow above the h1 and the answer sentence below it", () => {
    render(<PageHeader title="Moves" eyebrow="Moves · Week 9 · Colgate" answer={<>Add Cook for <b>+1.2</b></>} />);
    expect(screen.getByText("Moves · Week 9 · Colgate")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Moves" })).toBeInTheDocument();
    expect(screen.getByText(/Add Cook for/)).toBeInTheDocument();
  });

  it("renders neither without props", () => {
    const { container } = render(<PageHeader title="Moves" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });
});

describe("Section", () => {
  it("labels the region by its h2 and folds the method note", () => {
    render(<Section title="Adds" caption="Best pickups" howCalculated="Method text">body</Section>);
    expect(screen.getByRole("region", { name: "Adds" })).toBeInTheDocument();
    expect(screen.getByText("Best pickups")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "How this is calculated" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Method text")).toBeNull();
  });

  it("puts the method link on the heading row and opens the note below", async () => {
    render(<Section title="Adds" howCalculated="Method text">body</Section>);
    const toggle = screen.getByRole("button", { name: "How this is calculated" });
    expect(toggle.parentElement).toContainElement(screen.getByRole("heading", { name: "Adds" }));
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Method text")).toBeInTheDocument();
  });

  it("omits the disclosure without a method note", () => {
    render(<Section title="Adds">body</Section>);
    expect(screen.queryByText("How this is calculated")).toBeNull();
  });
});
