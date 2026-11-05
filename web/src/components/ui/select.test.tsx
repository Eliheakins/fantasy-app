import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

describe("Select", () => {
  it("styles the highlighted item so it stands out from the open list", async () => {
    render(
      <Select defaultValue="a">
        <SelectTrigger aria-label="Pick"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value="a">Alpha</SelectItem><SelectItem value="b">Beta</SelectItem></SelectContent>
      </Select>,
    );
    await userEvent.click(screen.getByRole("combobox", { name: "Pick" }));
    const item = await screen.findByRole("option", { name: "Beta" });
    expect(item.className).toContain("data-[highlighted]:bg-focus");
    expect(item.className).toContain("data-[highlighted]:text-white");
  });
});
