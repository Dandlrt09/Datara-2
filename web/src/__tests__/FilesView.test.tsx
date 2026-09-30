import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import FilesView from "../routes/FilesView";
import { ApiError } from "../lib/api";

const { useFilesMock, useFilesGlobalMock, useSessionsMock, useUploadFileMock, useDeleteFileMock, useCreateSessionMock, useFileSheetsMock, useSelectFileSheetMock, useProfileMock, useRenameFileMock } =
  vi.hoisted(() => ({
    useFilesMock: vi.fn(),
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
  useFiles: (sessionId: string | null) => useFilesMock(sessionId),
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

/** Shape returned by both paged file hooks (`useFiles` / `useFilesGlobal`). */
function listResult(overrides: Record<string, unknown> = {}) {
  return {
    data: [],
    isLoading: false,
    isSuccess: true,
    error: null,
    refetch: vi.fn(),
    hasMore: false,
    isLoadingMore: false,
    loadMore: vi.fn(),
    ...overrides,
  };
}

/** Switch the visible list to the cross-session view. */
function selectAllView() {
  fireEvent.click(screen.getByRole("radio", { name: "Todas las sesiones" }));
}

// The per-session endpoint returns `FileResponse` (no session metadata); the
// session view fills the Session column from the selected session.
const sessionFile = {
  id: 42,
  filename: "sales.csv",
  format: "csv",
  row_count: 10,
  size_bytes: 2048,
  created_at: "2024-01-01",
  has_profile: true,
};

// The global endpoint returns `FileListItem` (carries the session metadata).
const globalFile = {
  ...sessionFile,
  chat_session_id: "ses-1",
  session_title: "Session 1",
};

describe("FilesView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: one session, loading false
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Session 1" }],
      isLoading: false,
    });
    // Default: both list sources resolved and empty; the view defaults to the
    // session source, so most tests override `useFilesMock`.
    useFilesMock.mockReturnValue(listResult());
    useFilesGlobalMock.mockReturnValue(listResult());
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
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Files")).toBeTruthy();
  });

  it("defaults to 'Solo esta sesión' and queries the selected session", () => {
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));
    renderWithProviders(<FilesView />);

    const sessionRadio = screen.getByRole("radio", {
      name: "Solo esta sesión",
    }) as HTMLInputElement;
    expect(sessionRadio.checked).toBe(true);
    expect(useFilesMock).toHaveBeenCalledWith("ses-1");
    expect(screen.getByText("sales.csv")).toBeTruthy();
  });

  it("shows 'No hay archivos en esta sesión.' when the selected session has none", () => {
    renderWithProviders(<FilesView />);
    expect(screen.getByText("No hay archivos en esta sesión.")).toBeTruthy();
    expect(screen.queryByText("No files uploaded yet.")).toBeNull();
  });

  it("shows 'No files uploaded yet.' in 'Todas las sesiones'", () => {
    renderWithProviders(<FilesView />);
    selectAllView();
    expect(screen.getByText("No files uploaded yet.")).toBeTruthy();
    expect(screen.queryByText("No hay archivos en esta sesión.")).toBeNull();
  });

  it("renders the session picker", () => {
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Session 1")).toBeTruthy();
  });

  it("switching the session selector reacts without a reload", () => {
    useSessionsMock.mockReturnValue({
      data: [
        { id: "ses-1", title: "Session 1" },
        { id: "ses-2", title: "Session 2" },
      ],
      isLoading: false,
    });
    useFilesMock.mockImplementation((id: string | null) =>
      id === "ses-2"
        ? listResult({
            data: [{ ...sessionFile, id: 99, filename: "second.csv" }],
          })
        : listResult({ data: [sessionFile] }),
    );

    renderWithProviders(<FilesView />);
    expect(screen.getByText("sales.csv")).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "ses-2" },
    });

    expect(screen.getByText("second.csv")).toBeTruthy();
    expect(screen.queryByText("sales.csv")).toBeNull();
    expect(useFilesMock).toHaveBeenLastCalledWith("ses-2");
  });

  it("fills the Session column with the selected session's title in session view", () => {
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Alpha" }],
      isLoading: false,
    });
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));
    renderWithProviders(<FilesView />);

    // Role-scoped to the table cell, so the picker option does not collide.
    expect(screen.getByRole("cell", { name: "Alpha" })).toBeTruthy();
  });

  it("renders no list empty state when there are no sessions", () => {
    useSessionsMock.mockReturnValue({ data: [], isLoading: false });
    renderWithProviders(<FilesView />);

    expect(screen.queryByText("No hay archivos en esta sesión.")).toBeNull();
    expect(screen.queryByText("No files uploaded yet.")).toBeNull();
  });

  it("'Todas las sesiones' renders the global rows", () => {
    useFilesGlobalMock.mockReturnValue(listResult({ data: [globalFile] }));
    renderWithProviders(<FilesView />);
    selectAllView();

    expect(screen.getByText("sales.csv")).toBeTruthy();
  });

  it("shows the active view's error and retries that view", () => {
    const refetch = vi.fn();
    useFilesMock.mockReturnValue(
      listResult({
        data: [],
        error: new Error("Session files failed"),
        refetch,
      }),
    );
    renderWithProviders(<FilesView />);

    expect(screen.getByText("Session files failed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("shows the global error and retry in 'Todas las sesiones' (R-ErrorUI-1)", () => {
    useFilesGlobalMock.mockReturnValue(
      listResult({
        data: [],
        error: new Error("Failed to load files"),
      }),
    );
    renderWithProviders(<FilesView />);
    selectAllView();

    expect(screen.getByText("Failed to load files")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("shows upload error inline (R-ErrorUI-2)", () => {
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
    // Both global files and sessions fail; the global error surfaces in the
    // cross-session view (the session picker has no error surface).
    useFilesGlobalMock.mockReturnValue(
      listResult({
        data: [],
        error: new Error("Failed to load files"),
      }),
    );
    useSessionsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load sessions"),
      refetch: vi.fn(),
    });
    renderWithProviders(<FilesView />);
    selectAllView();
    // Must render error, never blank
    expect(screen.getByText("Failed to load files")).toBeTruthy(); // from ErrorCard message
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("when 0 sessions, shows 'Create a chat session' button and no dead-end text", () => {
    useSessionsMock.mockReturnValue({
      data: [],
      isLoading: false,
    });

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
    useFilesMock.mockReturnValue(
      listResult({
        data: [
          {
            id: 1,
            filename: "broken.xlsx",
            format: "xlsx",
            size_bytes: 1024,
            created_at: "2024-01-01",
            has_profile: false,
          },
        ],
      }),
    );
    renderWithProviders(<FilesView />);
    expect(screen.getByText("Not profiled")).toBeTruthy();
  });

  it("renders the tabular profile when useProfile returns a profile", () => {
    useFilesMock.mockReturnValue(
      listResult({
        data: [
          {
            id: 9,
            filename: "sales.csv",
            format: "csv",
            size_bytes: 1024,
            created_at: "2024-01-01",
            has_profile: true,
          },
        ],
      }),
    );
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
    useFilesMock.mockReturnValue(
      listResult({
        data: [
          {
            id: 7,
            filename: "book.xlsx",
            format: "xlsx",
            size_bytes: 2048,
            created_at: "2024-01-01",
            has_profile: true,
          },
        ],
      }),
    );
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
    useFilesMock.mockReturnValue(
      listResult({
        data: [
          {
            id: 8,
            filename: "one.xlsx",
            format: "xlsx",
            size_bytes: 1024,
            created_at: "2024-01-01",
            has_profile: true,
          },
        ],
      }),
    );
    useFileSheetsMock.mockReturnValue({
      data: { sheets: ["Only"], default_sheet: "Only" },
      isLoading: false,
    });

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Sheets" }));

    expect(screen.queryByText(/This workbook has/)).toBeNull();
  });

  it("clicking Delete opens the confirmation dialog and sends no request", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText('Delete "sales.csv"? This cannot be undone.')).toBeTruthy();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("confirming the dialog deletes the file with its id", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete file" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith(42);
  });

  it("cancelling the dialog sends no request", () => {
    const mutate = vi.fn();
    useDeleteFileMock.mockReturnValue({ mutate, isError: false, isPending: false });
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("disables the row delete trigger while a delete is pending", () => {
    useDeleteFileMock.mockReturnValue({ mutate: vi.fn(), isError: false, isPending: true });
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);

    const button = screen.getByRole("button", { name: "Delete" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("renders a file input whose accept list excludes .tab (F6)", () => {
    const { container } = renderWithProviders(<FilesView />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;

    expect(input).toBeTruthy();
    const accept = input?.getAttribute("accept") ?? "";
    expect(accept).not.toContain(".tab");
    expect(accept).toContain(".tsv");
  });

  it("shows 'Cargar más' for the active session view and calls its loadMore", () => {
    const loadMore = vi.fn();
    useFilesMock.mockReturnValue(
      listResult({ data: [sessionFile], hasMore: true, loadMore }),
    );

    renderWithProviders(<FilesView />);
    const button = screen.getByRole("button", { name: "Cargar más" });

    fireEvent.click(button);
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it("'Todas las sesiones' paginates the global list", () => {
    const loadMore = vi.fn();
    useFilesGlobalMock.mockReturnValue(
      listResult({ data: [globalFile], hasMore: true, loadMore }),
    );

    renderWithProviders(<FilesView />);
    selectAllView();
    fireEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it("hides 'Cargar más' when the active view has no more pages", () => {
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);
    expect(screen.queryByRole("button", { name: "Cargar más" })).toBeNull();
  });

  it("disables the button and shows 'Cargando…' while loading more", () => {
    useFilesMock.mockReturnValue(
      listResult({ data: [sessionFile], hasMore: true, isLoadingMore: true }),
    );

    renderWithProviders(<FilesView />);
    const button = screen.getByRole("button", { name: "Cargando…" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("renders a 'Descargar' link per row pointing at the download endpoint", () => {
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);
    const link = screen.getByRole("link", { name: "Descargar" }) as HTMLAnchorElement;

    expect(link.getAttribute("href")).toBe("/api/files/42/download");
    expect(link.getAttribute("download")).toBe("sales.csv");
  });

  it("formats the Rows and Size cells with Spanish separators", () => {
    useFilesMock.mockReturnValue(
      listResult({
        data: [
          {
            id: 55,
            filename: "big.csv",
            format: "csv",
            row_count: 1234567,
            size_bytes: 1536000,
            created_at: "2024-01-01",
            has_profile: true,
          },
        ],
      }),
    );

    renderWithProviders(<FilesView />);

    expect(screen.getByText("1.234.567")).toBeTruthy();
    expect(screen.getByText("1.500 KB")).toBeTruthy();
  });

  it("keeps the Sheets/Profile/Delete actions alongside Descargar", () => {
    useFilesMock.mockReturnValue(
      listResult({
        data: [
          {
            id: 43,
            filename: "book.xlsx",
            format: "xlsx",
            size_bytes: 2048,
            created_at: "2024-01-01",
            has_profile: true,
          },
        ],
      }),
    );
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
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

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
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

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
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

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
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

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
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

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
    useFilesMock.mockReturnValue(listResult({ data: [sessionFile] }));

    renderWithProviders(<FilesView />);

    expect(
      screen.getByText("La extensión del archivo no puede cambiar."),
    ).toBeTruthy();
  });
});