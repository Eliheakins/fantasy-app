import { render } from "@testing-library/react";
import { DataTableFallback } from "./DataTableFallback";

describe("DataTableFallback", () => {
  it("renders rows that repeat a time label without duplicate-key warnings", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<DataTableFallback columns={["Run", "Odds"]} rows={[["Oct 23, 12 PM", 40], ["Oct 23, 12 PM", 40], ["Oct 23, 12 PM", 41]]} />);
    expect(error).not.toHaveBeenCalled();
    error.mockRestore();
  });
});
