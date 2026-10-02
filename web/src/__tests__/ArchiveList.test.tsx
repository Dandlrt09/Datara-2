import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ArchiveList from "../routes/ArchiveList";
import type { Archive } from "../queries/useArchives";

const { useArchivesMock, useArchiveDetailMock } = vi.hoisted(() => ({
  useArchivesMock: vi.fn(),
  useArchiveDetailMock: vi.fn(),
}));

vi.mock("../queries/useArchives", () => ({
  useArchives: () => useArchivesMock(),
  useArchiveDetail: (id: number | null) => useArchiveDetailMock(id),
}));

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

function mockList(data: Archive[] | undefined, extra: Record<string, unknown> = {}) {
  useArchivesMock.mockReturnValue({
    data,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
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
    });
    renderWithProviders(<ArchiveList />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("No se pudieron cargar los análisis")).toBeTruthy();
    expect(screen.getByText("Reintentar")).toBeTruthy();
  });

  it("shows the loading copy", () => {
    mockList(undefined, { isLoading: true });
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

  it("filters by name case- and accent-insensitively", () => {
    mockList([
      makeArchive({ id: 1, name: "Margen por región" }),
      makeArchive({ id: 2, name: "Clientes sin compra" }),
    ]);
    renderWithProviders(<ArchiveList />);

    fireEvent.change(screen.getByLabelText("Buscar análisis"), {
      target: { value: "REGION" },
    });

    expect(screen.getByText("Margen por región")).toBeTruthy();
    expect(screen.queryByText("Clientes sin compra")).toBeNull();
  });

  it("shows a no-results message when the search matches nothing", () => {
    mockList([makeArchive({ name: "Margen por región" })]);
    renderWithProviders(<ArchiveList />);

    fireEvent.change(screen.getByLabelText("Buscar análisis"), {
      target: { value: "zzz" },
    });

    expect(screen.getByText("No se encontraron análisis")).toBeTruthy();
    expect(screen.queryByText("Margen por región")).toBeNull();
  });

  it("toggles the order between newest and oldest", () => {
    mockList([
      makeArchive({ id: 1, name: "Viejo", created_at: "2026-01-01 10:00:00" }),
      makeArchive({ id: 2, name: "Nuevo", created_at: "2026-06-01 10:00:00" }),
    ]);
    renderWithProviders(<ArchiveList />);

    const headings = () =>
      screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

    expect(headings()).toEqual(["Nuevo", "Viejo"]);
    fireEvent.click(screen.getByText("Más recientes"));
    expect(screen.getByText("Más antiguos")).toBeTruthy();
    expect(headings()).toEqual(["Viejo", "Nuevo"]);
  });

  it("lazily fetches detail: null until a card is expanded", () => {
    mockList([
      makeArchive({ id: 11, name: "Uno" }),
      makeArchive({ id: 22, name: "Dos" }),
    ]);
    renderWithProviders(<ArchiveList />);

    // No per-row fetch: the single hook is disabled (null) on mount.
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(null);
    expect(useArchiveDetailMock).not.toHaveBeenCalledWith(11);
    expect(useArchiveDetailMock).not.toHaveBeenCalledWith(22);
    expect(document.querySelector("pre")).toBeNull();

    fireEvent.click(screen.getAllByText("Ver detalle")[0]);
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(11);
    expect(screen.getAllByText("Ocultar detalle").length).toBe(1);
    expect(document.querySelector("pre")).toBeTruthy();

    fireEvent.click(screen.getByText("Ocultar detalle"));
    expect(useArchiveDetailMock).toHaveBeenLastCalledWith(null);
    expect(document.querySelector("pre")).toBeNull();
  });

  it("marks Reabrir / Exportar as inert (disabled, announced)", () => {
    mockList([makeArchive()]);
    renderWithProviders(<ArchiveList />);
    const reabrir = screen.getByRole("button", {
      name: "Reabrir — Disponible próximamente",
    }) as HTMLButtonElement;
    const exportar = screen.getByRole("button", {
      name: "Exportar — Disponible próximamente",
    }) as HTMLButtonElement;
    expect(reabrir.disabled).toBe(true);
    expect(exportar.disabled).toBe(true);
    expect(reabrir.title).toBe("Disponible próximamente");
    expect(exportar.title).toBe("Disponible próximamente");
  });
});
