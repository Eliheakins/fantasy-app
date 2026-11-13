import { render, screen } from "@testing-library/react";
import { Field } from "./Field";

describe("Field", () => {
  it("ties an error to its input: the message sits under it and the input is marked invalid and described by it", () => {
    render(<Field id="pw" label="Password" error="Use at least 12 characters." />);
    const input = screen.getByLabelText("Password");
    const message = screen.getByRole("alert");
    expect(message).toHaveTextContent("Use at least 12 characters.");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", message.id);
    expect(input).toHaveAccessibleDescription("Use at least 12 characters.");
  });

  it("has no error wiring without an error", () => {
    render(<Field id="pw" label="Password" error={null} />);
    const input = screen.getByLabelText("Password");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
