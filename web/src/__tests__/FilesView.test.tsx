import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import FilesView from "../routes/FilesView";

const { useFilesGlobalMock, useSessionsMock, useUploadFileMock, useDeleteFileMock, useCreateSessionMock } =
  vi.hoisted(() => ({
    useFilesGlobalMock: vi.fn(),
    useSessionsMock: vi.fn(),
    useUploadFileMock: vi.fn(),
    useDeleteFileMock: vi.fn(),
    useCreateSessionMock: vi.fn(),
  }));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => useFilesGlobalMock(),
  useUploadFile: () => useUploadFileMock(),
  useDeleteFile: () => useDeleteFileMock(),
  useProfile: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => useSessionsMock(),
  useCreateSession: () => useCreateSessionMock(),
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
    useCreateSessionMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
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

  it("shows Cancel button while upload is pending", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    useUploadFileMock.mockReturnValue({
      mutate: vi.fn(),
      isError: false,
      isPending: true,
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText("Cancel")).toBeTruthy();
  });

  it("shows 'Upload cancelled' instead of failure when aborted", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    const abortError = new Error("The operation was aborted.");
    abortError.name = "AbortError";
    useUploadFileMock.mockReturnValue({
      mutate: vi.fn(),
      isError: true,
      isPending: false,
      error: abortError,
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Upload cancelled")).toBeTruthy();
    expect(screen.queryByText(/Upload failed/i)).toBeNull();
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

  it("when 0 sessions, shows 'Create a chat session' button and no dead-end text", () => {
    useSessionsMock.mockReturnValue({
      data: [],
      isLoading: false,
    });
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    
    renderWithProviders(<FilesView />);
    
    // Should show the create session button
    expect(screen.getByText("Create a chat session")).toBeTruthy();
    // Should NOT show the old dead-end text
    expect(screen.queryByText("Create a chat session before uploading files")).toBeNull();
    // Should show helper text
    expect(screen.getByText("Create a chat session to upload files")).toBeTruthy();
  });

  it("shows error when session creation fails", () => {
    useSessionsMock.mockReturnValue({
      data: [],
      isLoading: false,
    });
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    
    const errorMessage = "Network error";
    useCreateSessionMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: true,
      error: new Error(errorMessage),
    });
    
    renderWithProviders(<FilesView />);
    
    expect(screen.getByText(`Failed to create session: ${errorMessage}`)).toBeTruthy();
  });

  it("shows 'Creating session...' while session creation is pending", () => {
    useSessionsMock.mockReturnValue({
      data: [],
      isLoading: false,
    });
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });
    
    useCreateSessionMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      isError: false,
    });
    
    renderWithProviders(<FilesView />);
    
    expect(screen.getByText("Creating session...")).toBeTruthy();
    expect(screen.getByText("Create a chat session")).toBeDisabled();
  });
});