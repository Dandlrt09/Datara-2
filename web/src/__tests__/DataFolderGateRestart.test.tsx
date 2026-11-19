import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { ApiError } from "../lib/api";

/* The data-folder gate and the decision flow talk to the network through the
 * shared `api` wrapper, so these tests mock that wrapper (not the hooks) and
 * let the real queries and mutation run. That way the latch and the refetch
 * behaviour live under test too. */
const { getMock, putMock, apiMock } = vi.hoisted(() => {
  const getMock = vi.fn();
  const putMock = vi.fn();
  return {
    getMock,
    putMock,
    apiMock: {
      get: getMock,
      post: vi.fn(),
      put: putMock,
      patch: vi.fn(),
      delete: vi.fn(),
    },
  };
});

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, api: apiMock };
});

vi.mock("../routes/FirstRunScreen", () => ({
  default: () => <div>first-run-screen</div>,
}));
vi.mock("../routes/LoginScreen", () => ({ default: () => <div>login-screen</div> }));
vi.mock("../routes/AppShell", () => ({ default: () => <div>app-shell</div> }));

import App from "../App";

const UNDECIDED = {
  decided: false,
  path: "/home/dan/datos",
  default_path: "/home/dan/.local/share/datara",
};
const DECIDED = { ...UNDECIDED, decided: true };

/* Reads queued for `GET /api/data-folder`; once drained the last one is served
 * again, so a refetch never falls into an undefined read. */
let folderReads: unknown[] = [];
let lastRead: unknown = null;

function readFolder() {
  if (folderReads.length > 0) lastRead = folderReads.shift();
  if (lastRead instanceof Error) return Promise.reject(lastRead);
  return Promise.resolve(lastRead);
}

beforeEach(() => {
  vi.clearAllMocks();
  folderReads = [];
  lastRead = null;
  getMock.mockImplementation((url: string) => {
    if (url === "/api/data-folder") return readFolder();
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  putMock.mockResolvedValue({
    ...DECIDED,
    path: "/otra/carpeta",
    synced_client: null,
  });
});

describe("data-folder gate restart latch (F1 / T2c, L12)", () => {
  it("renders the routes when the folder was already decided on this boot", async () => {
    folderReads = [DECIDED];

    renderWithProviders(<App />, { route: "/login" });

    expect(await screen.findByText("login-screen")).toBeTruthy();
    expect(
      screen.queryByText(/se usa a partir del próximo arranque/i),
    ).toBeNull();
  });

  it("shows the restart notice when this boot saw the folder undecided and then decided", async () => {
    folderReads = [UNDECIDED, DECIDED];

    renderWithProviders(<App />, { route: "/first-run" });

    // The undecided read shows the picker; decide through the real screen.
    expect(
      await screen.findByRole("heading", { name: /dónde guardamos tus datos/i }),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Usar la carpeta recomendada" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Continuar" }));

    expect(
      await screen.findByText(/se usa a partir del próximo arranque/i),
    ).toBeTruthy();
    expect(screen.queryByText("first-run-screen")).toBeNull();
  });

  it("keeps the notice after a later refetch returns decided", async () => {
    folderReads = [UNDECIDED, DECIDED];

    const { qc } = renderWithProviders(<App />, { route: "/first-run" });
    fireEvent.click(
      await screen.findByRole("button", { name: "Usar la carpeta recomendada" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Continuar" }));
    await screen.findByText(/se usa a partir del próximo arranque/i);

    // A refocus/refetch must not release the app back into the same boot.
    await qc.invalidateQueries({ queryKey: ["data-folder"] });

    await waitFor(() =>
      expect(
        screen.getByText(/se usa a partir del próximo arranque/i),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("first-run-screen")).toBeNull();
  });

  it("keeps failing open to the routes when the folder probe errors", async () => {
    folderReads = [new ApiError(500, { detail: "boom" })];

    renderWithProviders(<App />, { route: "/login" });

    expect(await screen.findByText("login-screen")).toBeTruthy();
  });
});
