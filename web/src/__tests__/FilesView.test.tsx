import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import FilesView from "../routes/FilesView";

const { useFilesGlobalMock, useSessionsMock, useUploadFileMock, useDeleteFileMock } =
  vi.hoisted(() => ({
    useFilesGlobalMock: vi.fn(),
    useSessionsMock: vi.fn(),
    useUploadFileMock: vi.fn(),
    useDeleteFileMock: vi.fn(),
  }));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => useFilesGlobalMock(),
  useUploadFile: () => useUploadFileMock(),
  useDeleteFile: () => useDeleteFileMock(),
  useProfile: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => useSessionsMock(),
}));

describe("FilesView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: one session, loading false
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Session 1" }],
      isLoading: false,
    });
    useUploadFileMock.mockReturnValue({
      mutate: vi.fn(),
      isError: false,
      isPending: false,
    });
    useDeleteFileMock.mockReturnValue({
      mutate: vi.fn(),
      isError: false,
      isPending: false,
    });
  });

  it("renders the heading", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Files")).toBeTruthy();
  });

  it("shows empty state when no files", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("No files uploaded yet.")).toBeTruthy();
  });

  it("renders the session picker", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Session 1")).toBeTruthy();
  });

  it("shows error card and retry on query failure (R-ErrorUI-1)", () => {
    useFilesGlobalMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Network error"),
      refetch: vi.fn(),
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("shows upload error inline (R-ErrorUI-2)", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    useUploadFileMock.mockReturnValue({
      mutate: vi.fn(),
      isError: true,
      isPending: false,
      error: new Error("Invalid file format"),
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Upload failed/i)).toBeTruthy();
  });

  it("__all__ regression: all endpoints reject → error + retry visible (R-TestWall-2)", () => {
    // Both global files and sessions fail
    useFilesGlobalMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load files"),
      refetch: vi.fn(),
    });
    useSessionsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load sessions"),
      refetch: vi.fn(),
    });
    renderWithProviders(<FilesView />);
    // Must render error, never blank
    expect(screen.getByText("Failed to load files")).toBeTruthy(); // from ErrorCard message
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});