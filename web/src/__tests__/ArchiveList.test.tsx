import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ArchiveList from "../routes/ArchiveList";
import type { Archive } from "../queries/useArchives";

const {
  useArchivesMock,
  useArchiveDetailMock,
  useDeleteArchiveMock,
  useRenameArchiveMock,
  navigateMock,
  apiGetMock,
  downloadTextFileMock,
} = vi.hoisted(() => ({
  useArchivesMock: vi.fn(),
  useArchiveDetailMock: vi.fn(),
  useDeleteArchiveMock: vi.fn(),
  useRenameArchiveMock: vi.fn(),
  navigateMock: vi.fn(),
  apiGetMock: vi.fn(),
  downloadTextFileMock: vi.fn(),
}));

vi.mock("../queries/useArchives", () => ({
  useArchives: (...args: unknown[]) => useArchivesMock(...args),
  useArchiveDetail: (id: number | null) => useArchiveDetailMock(id),
  useDeleteArchive: () => useDeleteArchiveMock(),
  useRenameArchive: () => useRenameArchiveMock(),
}));

vi.mock("../lib/api", () => ({
  api: {
    get: (...args: unknown[]) => apiGetMock(...args),
    patch: vi.fn(),
    delete: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock("../lib/archiveMarkdown", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../lib/archiveMarkdown")>();
  return {
    ...actual,
    downloadTextFile: (...args: unknown[]) => downloadTextFileMock(...args),
  };
});

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const DAY_MS = 24 * 60 * 60 * 1000;

function makeArchive(overrides: Partial<Archive> = {}): Archive {
  return {
    id: 1,
    name: "Margen por región",
    chat_session: "ses_1",
    created_at: new Date(Date.now() - 5 * DAY_MS).toISOString(),
    files: ["ventas_q3.csv"],
    row_count: 1000,
    column_count: 2,
    ...overrides,
  };
}

/** Return the infinite-query shape `ArchiveList` flattens. */
function mockList(data: Archive[] | undefined, extra: Record<string, unknown> = {}) {
  useArchivesMock.mockReturnValue({
    data: data === undefined ? undefined : { pages: [data] },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    hasNextPage: false,
    fetchNextPage: vi.fn(),
    isFetchingNextPage: false,
    ...extra,
  });
}

function mockDetail() {
  useArchiveDetailMock.mockImplementation((id: number | null) =>
    id == null
      ? { data: undefined, error: null, refetch: vi.fn() }
      : {
          data: { payload: { messages: [], files: [] } },
          error: null,
          refetch: vi.fn(),
        },
  );
}

describe("ArchiveList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDetail();
    useDeleteArchiveMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    useRenameArchiveMock.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    apiGetMock.mockResolvedValue({ payload: { messages: [], files: [] } });
  });

  it("renders the Spanish heading", () => {
    mockList([]);
    renderWithProviders(<ArchiveList />);
    expect(screen.getByText("Análisis")).toBeTruthy();
  });

  it("shows a Spanish error card and retry on failure", () => {
    useArchivesMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load archives"),
      refetch: vi.fn(),
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    });
    renderWithProviders(<ArchiveList />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("No se pudieron cargar los análisis")).toBeTruthy();
    expect(screen.getByText("Reintentar")).toBeTruthy();
  });

  it("shows the loading copy", () => {
    mockList([], { isLoading: true });
    renderWithProviders(<ArchiveList />);
    expect(screen.getByText("Cargando análisis…")).toBeTruthy();
  });

  it("shows the empty state with a link to the chat", () => {
    mockList([]);
    renderWithProviders(<ArchiveList />);
    expect(screen.getByText("Sube un archivo y pide un análisis")).toBeTruthy();
    const link = screen.getByRole("link", { name: "Ir al chat" });
    expect(link.getAttribute("href")).toBe("/app/chat");
  });

  it("renders title, file chip, relative time and summary", () => {
    mockList([makeArchive()]);
    renderWithProviders(<ArchiveList />);
    expect(screen.getByRole("heading", { level: 2, name: "Margen por región" })).toBeTruthy();
    expect(screen.getByText("ventas_q3.csv")).toBeTruthy();
    expect(screen.getByText("hace 5 días")).toBeTruthy();
    expect(screen.getByText("1.000 filas · 2 columnas")).toBeTruthy();
  });

  it("shows a +N chip when the snapshot has more than one file", () => {
    mockList([makeArchive({ files: ["a.csv", "b.csv", "c.csv"] })]);
    renderWithProviders(<ArchiveList />);
    expect(screen.getByText("a.csv")).toBeTruthy();
    expect(screen.getByText("+2")).toBeTruthy();
  });

  it("sends the search term to the server instead of filtering loaded pages", async () => {
    mockList([
      makeArchive({ id: 1, name: "Margen por región" }),
      makeArchive({ id: 2, name: "Clientes sin compra" }),
    ]);
    renderWithProviders(<ArchiveList />);

    fireEvent.change(screen.getByLabelText("Buscar análisis"), {
      target: { value: "REGION" },
    });

    await waitFor(() =>
      expect(useArchivesMock).toHaveBeenLastCalledWith({
        q: "REGION",
        order: "newest",
      }),
    );
    // No in-memory filter: both rows stay visible until the server returns the
    // filtered page.
    expect(screen.getByText("Margen por región")).toBeTruthy();
    expect(screen.getByText("Clientes sin compra")).toBeTruthy();
  });

  it("shows a no-results message when a server-backed search returns nothing", async () => {
    mockList([]);
    renderWithProviders(<ArchiveList />);

    fireEvent.change(screen.getByLabelText("Buscar análisis"), {
      target: { value: "zzz" },
    });

    expect(await screen.findByText("No se encontraron análisis")).toBeTruthy();
  });

  it("toggles the order by sending the order param", async () => {
    mockList([makeArchive({ id: 1, name: "Único" })]);
    renderWithProviders(<ArchiveList />);

    expect(useArchivesMock).toHaveBeenLastCalledWith({
      q: "",
      order: "newest",
    });

    fireEvent.click(screen.getByText("Más recientes"));

    expect(screen.getByText("Más antiguos")).toBeTruthy();
    await waitFor(() =>
      expect(useArchivesMock).toHaveBeenLastCalledWith({
        q: "",
        order: "oldest",
      }),
    );
  });

  it("renders an em dash for a null created_at", () => {
    mockList([makeArchive({ id: 1, name: "Sin fecha", created_at: null })]);
    renderWithProviders(<ArchiveList />);

    expect(
      screen.getByRole("heading", { level: 2, name: "Sin fecha" }),
    ).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("lazily fetches the detail and renders the snapshot when expanded", () => {
    mockList([
      makeArchive({ id: 11, name: "Uno" }),
      makeArchive({ id: 22, name: "Dos" }),
    ]);
    renderWithProviders(<ArchiveList />);

    // No per-row fetch: the single hook is disabled (null) on mount.
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(null);
    expect(useArchiveDetailMock).not.toHaveBeenCalledWith(11);
    expect(useArchiveDetailMock).not.toHaveBeenCalledWith(22);

    fireEvent.click(screen.getAllByText("Ver detalle")[0]);
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(11);
    expect(screen.getByRole("heading", { level: 3, name: "Uno" })).toBeTruthy();

    fireEvent.click(screen.getByText("Ocultar detalle"));
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(null);
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
  });

  it("Reabrir with a live session navigates to the chat", () => {
    mockList([makeArchive({ chat_session: "ses_1" })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Reabrir"));

    expect(navigateMock).toHaveBeenCalledWith("/app/chat/ses_1");
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(null);
  });

  it("Reabrir with a null session opens the read-only snapshot", () => {
    mockList([makeArchive({ id: 7, name: "Sin sesión", chat_session: null })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Reabrir"));

    expect(navigateMock).not.toHaveBeenCalled();
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(7);
    expect(screen.getByRole("heading", { level: 3, name: "Sin sesión" })).toBeTruthy();
  });

  it("Exportar fetches the detail and downloads the Markdown", async () => {
    mockList([makeArchive({ name: "Margen por región" })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Exportar"));

    await waitFor(() => expect(downloadTextFileMock).toHaveBeenCalledTimes(1));
    expect(apiGetMock).toHaveBeenCalledWith("/api/archives/1");
    const [markdown, filename] = downloadTextFileMock.mock.calls[0];
    expect(markdown).toContain("# Margen por región");
    expect(filename).toBe("Margen por región.md");
  });

  it("Renombrar opens the inline editor and calls the mutation", () => {
    const mutate = vi.fn();
    useRenameArchiveMock.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    mockList([makeArchive({ id: 1 })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Renombrar"));
    const input = screen.getByLabelText("Nuevo nombre del análisis");
    fireEvent.change(input, { target: { value: "Nuevo nombre" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(mutate).toHaveBeenCalledWith(
      { id: 1, name: "Nuevo nombre" },
      expect.anything(),
    );
  });

  it("Borrar opens the confirm dialog and confirms the deletion", () => {
    const mutate = vi.fn();
    useDeleteArchiveMock.mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
    });
    mockList([makeArchive({ id: 1, name: "Margen por región" })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Borrar"));

    const dialog = screen.getByRole("dialog", { name: "Borrar análisis" });
    expect(
      within(dialog).getByText("Se borrará «Margen por región». Esta acción no se puede deshacer."),
    ).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Borrar" }));
    expect(mutate).toHaveBeenCalledWith(1, expect.anything());
  });

  it("shows «Cargar más» only while hasNextPage and calls fetchNextPage", () => {
    const fetchNextPage = vi.fn();
    useArchivesMock.mockReturnValue({
      data: { pages: [[makeArchive()]] },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      hasNextPage: true,
      fetchNextPage,
      isFetchingNextPage: false,
    });
    renderWithProviders(<ArchiveList />);

    const button = screen.getByText("Cargar más");
    fireEvent.click(button);
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("hides «Cargar más» when there is no next page", () => {
    mockList([makeArchive()]);
    renderWithProviders(<ArchiveList />);
    expect(screen.queryByText("Cargar más")).toBeNull();
  });

  it("surfaces an inline error when Exportar fails", async () => {
    apiGetMock.mockRejectedValueOnce(new Error("network down"));
    mockList([makeArchive({ name: "Margen por región" })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Exportar"));

    await waitFor(() =>
      expect(screen.getByText("No se pudo exportar el análisis")).toBeTruthy(),
    );
    expect(downloadTextFileMock).not.toHaveBeenCalled();
  });

  it("sanitizes path separators in the exported filename", async () => {
    mockList([makeArchive({ name: "Informe/2026\\Q3" })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.click(screen.getByText("Exportar"));

    await waitFor(() => expect(downloadTextFileMock).toHaveBeenCalledTimes(1));
    const [, filename] = downloadTextFileMock.mock.calls[0];
    expect(filename).toBe("Informe-2026-Q3.md");
  });

  it("surfaces a delete failure as a list-level alert", () => {
    useDeleteArchiveMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: true,
      error: {},
    });
    mockList([makeArchive({ id: 1 })]);
    renderWithProviders(<ArchiveList />);

    expect(screen.getByRole("alert").textContent).toContain(
      "No se pudo borrar el análisis",
    );
  });

  it("no longer shows the removed partial-coverage notices", async () => {
    useArchivesMock.mockReturnValue({
      data: { pages: [[makeArchive()]] },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      hasNextPage: true,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    });
    renderWithProviders(<ArchiveList />);

    fireEvent.change(screen.getByLabelText("Buscar análisis"), {
      target: { value: "margen" },
    });
    fireEvent.click(screen.getByText("Más recientes"));

    expect(screen.getByText("Más antiguos")).toBeTruthy();
    await waitFor(() =>
      expect(useArchivesMock).toHaveBeenLastCalledWith({
        q: "margen",
        order: "oldest",
      }),
    );
    expect(
      screen.queryByText(/solo cubre los análisis cargados/),
    ).toBeNull();
    expect(
      screen.queryByText(/solo ordena los análisis cargados/),
    ).toBeNull();
  });
});
