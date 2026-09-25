import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import FilesView from "../routes/FilesView";

const { useFilesGlobalMock, useSessionsMock, useUploadFileMock, useDeleteFileMock, useCreateSessionMock, useFileSheetsMock, useSelectFileSheetMock } =
  vi.hoisted(() => ({
    useFilesGlobalMock: vi.fn(),
    useSessionsMock: vi.fn(),
    useUploadFileMock: vi.fn(),
    useDeleteFileMock: vi.fn(),
    useCreateSessionMock: vi.fn(),
    useFileSheetsMock: vi.fn(),
    useSelectFileSheetMock: vi.fn(),
  }));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => useFilesGlobalMock(),
  useUploadFile: () => useUploadFileMock(),
  useDeleteFile: () => useDeleteFileMock(),
  useProfile: () => ({ data: undefined, isLoading: false }),
  useFileSheets: () => useFileSheetsMock(),
  useSelectFileSheet: () => useSelectFileSheetMock(),
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
    useFileSheetsMock.mockReturnValue({ data: undefined, isLoading: false });
    useSelectFileSheetMock.mockReturnValue({
      mutateAsync: vi.fn(),
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
    // The button should be disabled
    const button = screen.getByRole("button", { name: /Creating session.../ }) as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.disabled).toBe(true);
  });

  it("renders a 'Not profiled' badge when a file has no profile", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [
        {
          id: 1,
          filename: "broken.xlsx",
          format: "xlsx",
          size_bytes: 1024,
          created_at: "2024-01-01",
          chat_session_id: "ses-1",
          session_title: "Session 1",
          has_profile: false,
        },
      ],
      isLoading: false,
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Not profiled")).toBeTruthy();
  });

  it("shows the sheet warning for a multi-sheet xlsx row", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [
        {
          id: 7,
          filename: "book.xlsx",
          format: "xlsx",
          size_bytes: 2048,
          created_at: "2024-01-01",
          chat_session_id: "ses-1",
          session_title: "Session 1",
          has_profile: true,
        },
      ],
      isLoading: false,
    });
    useFileSheetsMock.mockReturnValue({
      data: { sheets: ["Data", "Meta"], default_sheet: "Data" },
      isLoading: false,
    });

    renderWithProviders(<FilesView />);
    // The sheet list is lazy: nothing fetched/shown until the row is opened.
    expect(screen.queryByText(/This workbook has/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Sheets" }));

    expect(screen.getByText("This workbook has 2 sheets")).toBeTruthy();
  });

  it("does not show the sheet warning for a single-sheet xlsx row", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [
        {
          id: 8,
          filename: "one.xlsx",
          format: "xlsx",
          size_bytes: 1024,
          created_at: "2024-01-01",
          chat_session_id: "ses-1",
          session_title: "Session 1",
          has_profile: true,
        },
      ],
      isLoading: false,
    });
    useFileSheetsMock.mockReturnValue({
      data: { sheets: ["Only"], default_sheet: "Only" },
      isLoading: false,
    });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Sheets" }));

    expect(screen.queryByText(/This workbook has/)).toBeNull();
  });

  const deletableFile = {
    id: 42,
    filename: "sales.csv",
    format: "csv",
    row_count: 10,
    size_bytes: 2048,
    created_at: "2024-01-01",
    chat_session_id: "ses-1",
    session_title: "Session 1",
    has_profile: true,
  };

  it("clicking Delete opens the confirmation dialog and sends no request", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText('Delete "sales.csv"? This cannot be undone.')).toBeTruthy();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("confirming the dialog deletes the file with its id", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete file" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith(42);
  });

  it("cancelling the dialog sends no request", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("disables the row delete trigger while a delete is pending", () => {
    useDeleteFileMock.mockReturnValue({ mutate: vi.fn(), isError: false, isPending: true });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false });

    renderWithProviders(<FilesView />);

    const button = screen.getByRole("button", { name: "Delete" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("renders a file input whose accept list excludes .tab (F6)", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false });

    const { container } = renderWithProviders(<FilesView />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;

    expect(input).toBeTruthy();
    const accept = input?.getAttribute("accept") ?? "";
    expect(accept).not.toContain(".tab");
    expect(accept).toContain(".tsv");
  });
});
