import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ArchiveList from "../routes/ArchiveList";

const { useArchivesMock, useArchiveDetailMock } = vi.hoisted(() => ({
  useArchivesMock: vi.fn(),
  useArchiveDetailMock: vi.fn(),
}));

vi.mock("../queries/useArchives", () => ({
  useArchives: () => useArchivesMock(),
  useArchiveDetail: () => useArchiveDetailMock(),
}));

describe("ArchiveList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useArchiveDetailMock.mockReturnValue({
      data: undefined,
      isLoading: false,
    });
  });

  it("renders the heading", () => {
    useArchivesMock.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<ArchiveList />);
    expect(screen.getByText("Archives")).toBeTruthy();
  });

  it("shows error card and retry on failure (R-ErrorUI-4)", () => {
    useArchivesMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load archives"),
      refetch: vi.fn(),
    });
    renderWithProviders(<ArchiveList />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Failed to load archives/i)).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
  });
});