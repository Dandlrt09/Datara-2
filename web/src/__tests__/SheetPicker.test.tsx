import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { SheetPicker } from "../components/SheetPicker";

const { useSelectFileSheetMock } = vi.hoisted(() => ({
  useSelectFileSheetMock: vi.fn(),
}));

vi.mock("../queries/useFiles", () => ({
  useSelectFileSheet: () => useSelectFileSheetMock(),
}));

describe("SheetPicker", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("names the sheet count and applies the selected sheet", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      file_id: 1,
      filename: "book.xlsx",
      sheet_name: "Meta",
      sheets: ["Data", "Meta"],
      row_count: 2,
    });
    useSelectFileSheetMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
    });
    const onSelected = vi.fn();

    renderWithProviders(
      <SheetPicker
        fileId={1}
        sheets={["Data", "Meta"]}
        currentSheet="Data"
        onSelected={onSelected}
      />
    );

    expect(screen.getByText("This workbook has 2 sheets")).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "Meta" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze this sheet" }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ fileId: 1, sheetName: "Meta" })
    );
    await waitFor(() => expect(onSelected).toHaveBeenCalled());
  });

  it("disables the apply button while the switch is pending", () => {
    useSelectFileSheetMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
      isError: false,
    });

    renderWithProviders(
      <SheetPicker fileId={1} sheets={["a", "b"]} currentSheet="a" />
    );

    const button = screen.getByRole("button") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("Applying…")).toBeTruthy();
  });

  it("surfaces the switch error in the warning card", () => {
    useSelectFileSheetMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: true,
      error: new Error("Sheet 'X' not found"),
    });

    renderWithProviders(
      <SheetPicker fileId={1} sheets={["a", "b"]} currentSheet="a" />
    );

    expect(screen.getByText("Sheet 'X' not found")).toBeTruthy();
  });
});
