/* F5 / S5 — the crossing panel of the chat screen.
 *
 * The seams the app uses for data are React Query hooks; these tests mock the
 * crossing hooks themselves (the same seam `FilesView.test.tsx` uses) and drive
 * the panel through the DOM. Every user-facing string here is the EXACT neutral
 * Spanish copy S5 requires, so a drift in the component fails loudly.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, act } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import CrossingPanel from "../components/CrossingPanel";
import type { ProfileSummary } from "../queries/useFiles";
import type { Crossing } from "../queries/useCrossings";

const {
  useCrossingFilesMock,
  useCrossingProfileMock,
  useCrossingMock,
  proposeMock,
  confirmMock,
  deleteMock,
} = vi.hoisted(() => ({
  useCrossingFilesMock: vi.fn(),
  useCrossingProfileMock: vi.fn(),
  useCrossingMock: vi.fn(),
  proposeMock: vi.fn(),
  confirmMock: vi.fn(),
  deleteMock: vi.fn(),
}));

vi.mock("../queries/useCrossings", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../queries/useCrossings")>();
  return {
    // The invalidation test swaps this for the real hook, so it exercises the
    // production query key through a real React Query cache.
    useCrossingFiles: (sessionId: string | null) =>
      useCrossingFilesMock(sessionId, actual.useCrossingFiles),
    useCrossingProfile: (fileId: number | null) => useCrossingProfileMock(fileId),
    useCrossing: (sessionId: string | null) => useCrossingMock(sessionId),
    useProposeCrossing: () => ({ mutateAsync: proposeMock, isPending: false }),
    useConfirmCrossing: () => ({ mutateAsync: confirmMock, isPending: false }),
    useDeleteCrossing: () => ({ mutateAsync: deleteMock, isPending: false }),
  };
});

const leftFile = {
  id: 1,
  filename: "a.csv",
  format: "csv",
  size_bytes: 2048,
  row_count: 5,
  has_profile: true,
};
const rightFile = {
  id: 2,
  filename: "b.csv",
  format: "csv",
  size_bytes: 2048,
  row_count: 4,
  has_profile: true,
};

const profiles: Record<number, ProfileSummary> = {
  1: {
    file_id: 1,
    schema: {
      columns: [
        { name: "id", dtype: "int64" },
        { name: "name", dtype: "object" },
      ],
    },
    stats: {},
    sample: [],
  },
  2: {
    file_id: 2,
    schema: {
      columns: [
        { name: "customer_id", dtype: "int64" },
        { name: "amount", dtype: "float64" },
      ],
    },
    stats: {},
    sample: [],
  },
};

const activeCrossing: Crossing = {
  id: 7,
  chat_session: "ses-1",
  left_file_id: 1,
  right_file_id: 2,
  left_key: "id",
  right_key: "customer_id",
  how: "inner",
  left_filename: "a.csv",
  right_filename: "b.csv",
};

/** Mutable GET result so a test can flip the active crossing between renders. */
let crossingState: Crossing | null = null;

/** Open the collapsed picker by its toggle. */
function openPanel() {
  fireEvent.click(screen.getByRole("button", { name: "Cruzar archivos" }));
}

/** Pick both files in the two file selects. */
function pickFiles() {
  fireEvent.change(screen.getByLabelText("Archivo izquierdo"), {
    target: { value: "1" },
  });
  fireEvent.change(screen.getByLabelText("Archivo derecho"), {
    target: { value: "2" },
  });
}

/** Minimal `fetch` response for the real file read used by the invalidation test. */
function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe("CrossingPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    crossingState = null;
    useCrossingFilesMock.mockReturnValue({
      data: [leftFile, rightFile],
      isLoading: false,
      error: null,
    });
    useCrossingProfileMock.mockImplementation((fileId: number | null) => ({
      data: fileId != null ? profiles[fileId] : undefined,
      isLoading: false,
      error: null,
    }));
    useCrossingMock.mockImplementation(() => ({
      data: { crossing: crossingState },
      isLoading: false,
      error: null,
    }));
    proposeMock.mockReset();
    confirmMock.mockReset();
    deleteMock.mockReset();
  });

  it("shows nothing with a single file in the session", () => {
    useCrossingFilesMock.mockReturnValue({
      data: [leftFile],
      isLoading: false,
      error: null,
    });
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);
    expect(screen.queryByText("Cruzar archivos")).toBeNull();
    expect(screen.queryByText("Archivo izquierdo")).toBeNull();
  });

  it("pre-selects the proposed columns and the join kind", async () => {
    proposeMock.mockResolvedValue({
      proposal: {
        left_key: "id",
        right_key: "customer_id",
        how: "left",
        reason: "Both datasets share a customer id.",
      },
      code: null,
    } as unknown);
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    openPanel();
    pickFiles();
    fireEvent.click(screen.getByRole("button", { name: "Proponer cruce" }));

    await waitFor(() =>
      expect(
        screen.getByText("El modelo propone cruzar por «id» = «customer_id»."),
      ).toBeTruthy(),
    );
    // The model's reason is secondary detail, allowed next to the proposal.
    expect(screen.getByText("Both datasets share a customer id.")).toBeTruthy();
    expect(
      (screen.getByLabelText("Columna del archivo izquierdo") as HTMLSelectElement)
        .value,
    ).toBe("id");
    expect(
      (screen.getByLabelText("Columna del archivo derecho") as HTMLSelectElement)
        .value,
    ).toBe("customer_id");
    expect(
      (screen.getByLabelText("Tipo de cruce") as HTMLSelectElement).value,
    ).toBe("left");
  });

  it("writes its own copy when the model finds no column", async () => {
    proposeMock.mockResolvedValue({
      proposal: null,
      code: "proposal_not_found",
      reason: "I could not find a shared key between the two datasets.",
    } as unknown);
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    openPanel();
    pickFiles();
    fireEvent.click(screen.getByRole("button", { name: "Proponer cruce" }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "El modelo no encontró una columna para cruzar. Elige las columnas a mano.",
        ),
      ).toBeTruthy(),
    );
    // The server's reason is English prose: it must never be the main message.
    expect(
      screen.queryByText(
        "I could not find a shared key between the two datasets.",
      ),
    ).toBeNull();
    expect(
      (screen.getByLabelText("Columna del archivo izquierdo") as HTMLSelectElement)
        .value,
    ).toBe("");
  });

  it("writes its own copy when the model cannot be consulted", async () => {
    proposeMock.mockResolvedValue({
      proposal: null,
      code: "proposal_unavailable",
      reason: "Missing credentials",
    } as unknown);
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    openPanel();
    pickFiles();
    fireEvent.click(screen.getByRole("button", { name: "Proponer cruce" }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "No se pudo consultar al modelo. Prueba de nuevo o elige las columnas a mano.",
        ),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("Missing credentials")).toBeNull();
  });

  it("reports the imbalance of the confirmation exactly as returned", async () => {
    confirmMock.mockResolvedValue({
      ...activeCrossing,
      diagnostics: {
        left_rows: 5,
        right_rows: 4,
        matched_rows: 3,
        left_only_rows: 2,
        right_only_rows: 1,
        result_rows: 6,
      },
    } as unknown);
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    openPanel();
    pickFiles();
    fireEvent.change(screen.getByLabelText("Columna del archivo izquierdo"), {
      target: { value: "name" },
    });
    fireEvent.change(screen.getByLabelText("Columna del archivo derecho"), {
      target: { value: "amount" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar cruce" }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "6 filas en el resultado · 3 coincidencias · 2 quedaron afuera de «a.csv» · 1 quedaron afuera de «b.csv».",
        ),
      ).toBeTruthy(),
    );
    expect(confirmMock).toHaveBeenCalledWith({
      left_file_id: 1,
      right_file_id: 2,
      left_key: "name",
      right_key: "amount",
      how: "inner",
    });
  });

  it("shows an active crossing with no numbers after a load", () => {
    crossingState = activeCrossing;
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    expect(
      screen.getByText(
        "Cruce activo: «a.csv» y «b.csv» por «id» = «customer_id»",
      ),
    ).toBeTruthy();
    // The stored recipe carries no diagnostics and they are never re-measured.
    expect(screen.queryByText(/filas en el resultado/)).toBeNull();
    expect(screen.queryByText(/coincidencias/)).toBeNull();
  });

  it("removes the active crossing", async () => {
    crossingState = activeCrossing;
    deleteMock.mockImplementation(async () => {
      crossingState = null;
    });
    const view = renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Quitar cruce" }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalled());

    view.rerender(<CrossingPanel sessionId="ses-1" />);
    expect(screen.queryByText(/Cruce activo/)).toBeNull();
  });

  it("reports a failed request and keeps the panel usable", async () => {
    proposeMock.mockRejectedValue(new Error("network down"));
    renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    openPanel();
    pickFiles();
    fireEvent.click(screen.getByRole("button", { name: "Proponer cruce" }));

    await waitFor(() =>
      expect(
        screen.getByText("No se pudo guardar el cruce. Prueba de nuevo."),
      ).toBeTruthy(),
    );
    // The toggle and the controls are still there for a retry.
    expect(
      screen.getByRole("button", { name: "Cruzar archivos" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Proponer cruce" }),
    ).toBeTruthy();
  });

  it("reveals the toggle when a file mutation invalidates the files family", async () => {
    // The network answers "zero files" first and "two files" after the
    // invalidation every file mutation performs (upload/delete/rename/sheet).
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse([leftFile, rightFile]));
    vi.stubGlobal("fetch", fetchMock);

    // Drive the panel through the REAL file read, so what gets invalidated is
    // the production query key and not a string this test hardcodes.
    useCrossingFilesMock.mockImplementation(
      (_sessionId: string | null, realHook: (id: string | null) => unknown) =>
        realHook("ses-1"),
    );

    const view = renderWithProviders(<CrossingPanel sessionId="ses-1" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Cruzar archivos")).toBeNull();

    // The real contract the file mutations use (useFiles.ts).
    await act(async () => {
      await view.qc.invalidateQueries({ queryKey: ["files"] });
    });

    await waitFor(() =>
      expect(screen.getByText("Cruzar archivos")).toBeTruthy(),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
