import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import FilesView from "../routes/FilesView";
import { ApiError } from "../lib/api";

const { useFilesGlobalMock, useSessionsMock, useUploadFileMock, useDeleteFileMock, useCreateSessionMock, useFileSheetsMock, useSelectFileSheetMock, useProfileMock, useRenameFileMock } =
  vi.hoisted(() => ({
    useFilesGlobalMock: vi.fn(),
    useSessionsMock: vi.fn(),
    useUploadFileMock: vi.fn(),
    useDeleteFileMock: vi.fn(),
    useCreateSessionMock: vi.fn(),
    useFileSheetsMock: vi.fn(),
    useSelectFileSheetMock: vi.fn(),
    useProfileMock: vi.fn(),
    useRenameFileMock: vi.fn(),
  }));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => useFilesGlobalMock(),
  useUploadFile: () => useUploadFileMock(),
  useDeleteFile: () => useDeleteFileMock(),
  useProfile: () => useProfileMock(),
  useFileSheets: () => useFileSheetsMock(),
  useSelectFileSheet: () => useSelectFileSheetMock(),
  useRenameFile: () => useRenameFileMock(),
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
    useProfileMock.mockReturnValue({ data: undefined, isLoading: false });
    useSelectFileSheetMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
    });
    useRenameFileMock.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
  });

  it("renders the heading", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Files")).toBeTruthy();
  });

  it("shows empty state when no files", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("No files uploaded yet.")).toBeTruthy();
  });

  it("renders the session picker", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Session 1")).toBeTruthy();
  });

  it("shows error card and retry on query failure (R-ErrorUI-1)", () => {
    useFilesGlobalMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Network error"),
      refetch: vi.fn(),
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("shows upload error inline (R-ErrorUI-2)", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
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
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
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
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
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
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
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
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
    
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
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
    
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
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });
    
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
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
    });
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Not profiled")).toBeTruthy();
  });

  it("renders the tabular profile when useProfile returns a profile", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [
        {
          id: 9,
          filename: "sales.csv",
          format: "csv",
          size_bytes: 1024,
          created_at: "2024-01-01",
          chat_session_id: "ses-1",
          session_title: "Session 1",
          has_profile: true,
        },
      ],
      isLoading: false,
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
    });
    useProfileMock.mockReturnValue({
      data: {
        file_id: 9,
        schema: { columns: [{ name: "amount", dtype: "int64" }] },
        stats: { amount: { null_count: 0, unique_count: 2, min: 1, max: 9 } },
        sample: [],
        generated_at: "2024-01-01T00:00:00Z",
      },
      isLoading: false,
    });

    renderWithProviders(<FilesView />);

    expect(screen.getByRole("columnheader", { name: "Tipo" })).toBeTruthy();
    expect(screen.getByText("amount")).toBeTruthy();
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
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
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
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
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
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText('Delete "sales.csv"? This cannot be undone.')).toBeTruthy();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("confirming the dialog deletes the file with its id", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete file" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith(42);
  });

  it("cancelling the dialog sends no request", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("disables the row delete trigger while a delete is pending", () => {
    useDeleteFileMock.mockReturnValue({ mutate: vi.fn(), isError: false, isPending: true });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);

    const button = screen.getByRole("button", { name: "Delete" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("renders a file input whose accept list excludes .tab (F6)", () => {
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    const { container } = renderWithProviders(<FilesView />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;

    expect(input).toBeTruthy();
    const accept = input?.getAttribute("accept") ?? "";
    expect(accept).not.toContain(".tab");
    expect(accept).toContain(".tsv");
  });

  it("shows 'Cargar más' when more pages exist and calls loadMore on click", () => {
    const loadMore = vi.fn();
    useFilesGlobalMock.mockReturnValue({
      data: [deletableFile],
      isLoading: false,
      hasMore: true,
      isLoadingMore: false,
      loadMore,
    });

    renderWithProviders(<FilesView />);
    const button = screen.getByRole("button", { name: "Cargar más" });

    fireEvent.click(button);
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it("hides 'Cargar más' when there are no more pages", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [deletableFile],
      isLoading: false,
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
    });

    renderWithProviders(<FilesView />);
    expect(screen.queryByRole("button", { name: "Cargar más" })).toBeNull();
  });

  it("disables the button and shows 'Cargando…' while loading more", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [deletableFile],
      isLoading: false,
      hasMore: true,
      isLoadingMore: true,
      loadMore: vi.fn(),
    });

    renderWithProviders(<FilesView />);
    const button = screen.getByRole("button", { name: "Cargando…" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("renders a 'Descargar' link per row pointing at the download endpoint", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [deletableFile],
      isLoading: false,
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
    });

    renderWithProviders(<FilesView />);
    const link = screen.getByRole("link", { name: "Descargar" }) as HTMLAnchorElement;

    expect(link.getAttribute("href")).toBe("/api/files/42/download");
    expect(link.getAttribute("download")).toBe("sales.csv");
  });

  it("keeps the Sheets/Profile/Delete actions alongside Descargar", () => {
    useFilesGlobalMock.mockReturnValue({
      data: [
        {
          id: 43,
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
      hasMore: false,
      isLoadingMore: false,
      loadMore: vi.fn(),
    });
    useProfileMock.mockReturnValue({
      data: {
        file_id: 43,
        schema: { columns: [{ name: "amount", dtype: "int64" }] },
        stats: { amount: { null_count: 0, unique_count: 2, min: 1, max: 9 } },
        sample: [],
        generated_at: "2024-01-01T00:00:00Z",
      },
      isLoading: false,
    });
    useFileSheetsMock.mockReturnValue({
      data: { sheets: ["Data", "Meta"], default_sheet: "Data" },
      isLoading: false,
    });

    renderWithProviders(<FilesView />);

    expect(screen.getByRole("link", { name: "Descargar" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sheets" })).toBeTruthy();
    expect(screen.getByText("Profile")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });

  it("Renombrar opens an inline editor prefilled with the current name", () => {
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Renombrar" }));

    const input = screen.getByLabelText("Nuevo nombre del archivo") as HTMLInputElement;
    expect(input.value).toBe("sales.csv");
    expect(screen.getByRole("button", { name: "Guardar" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeTruthy();
  });

  it("Guardar sends the trimmed name and closes the editor on success", () => {
    const mutate = vi.fn((_vars: unknown, opts?: { onSuccess?: () => void }) =>
      opts?.onSuccess?.(),
    );
    useRenameFileMock.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Renombrar" }));
    fireEvent.change(screen.getByLabelText("Nuevo nombre del archivo"), {
      target: { value: "  renamed.csv  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(mutate).toHaveBeenCalledWith(
      { fileId: 42, filename: "renamed.csv" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(screen.queryByLabelText("Nuevo nombre del archivo")).toBeNull();
  });

  it("Cancelar closes the editor without sending a request", () => {
    const mutate = vi.fn();
    useRenameFileMock.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Renombrar" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Nuevo nombre del archivo")).toBeNull();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("Cancelar clears the rename error so it cannot linger", () => {
    const resetMock = vi.fn();
    useRenameFileMock.mockReturnValue({
      mutate: vi.fn(),
      reset: resetMock,
      isPending: false,
      isError: true,
      error: new ApiError(409, {
        detail: "A file named 'a.csv' already exists in this session.",
      }),
    });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);
    // Opening the editor already resets once; clear that call so the assertion
    // isolates the Cancelar path. The mocked hook's isError is static, so we
    // cannot assert the alert disappears — we pin the reset mechanism instead.
    fireEvent.click(screen.getByRole("button", { name: "Renombrar" }));
    resetMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(resetMock).toHaveBeenCalled();
  });

  it("surfaces a rename failure inline", () => {
    useRenameFileMock.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: true,
      error: new ApiError(409, {
        detail: "A file named 'a.csv' already exists in this session.",
      }),
    });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);

    expect(
      screen.getByText("A file named 'a.csv' already exists in this session."),
    ).toBeTruthy();
  });

  it("surfaces a rename failure inline for the 422 object detail shape", () => {
    useRenameFileMock.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: true,
      error: new ApiError(422, {
        detail: {
          code: "invalid_filename",
          message: "La extensión del archivo no puede cambiar.",
        },
      }),
    });
    useFilesGlobalMock.mockReturnValue({ data: [deletableFile], isLoading: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn() });

    renderWithProviders(<FilesView />);

    expect(
      screen.getByText("La extensión del archivo no puede cambiar."),
    ).toBeTruthy();
  });
});
