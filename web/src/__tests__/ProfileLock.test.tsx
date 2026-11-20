import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ProfileView from "../routes/ProfileView";

/* The lock section talks to the network through the shared hooks, so these
 * tests mock `useAuth` (like `ProfileView.test.tsx`) and `useAppConfig`, and
 * let the real components render. That way the local-only gating and the
 * one-time key reveal live under test. */
const { useMeMock, useAppConfigMock, statusMock, lockState } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useAppConfigMock: vi.fn(),
  statusMock: vi.fn(),
  lockState: { mutate: vi.fn(), isPending: false },
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useUpdateName: () => ({ mutate: vi.fn(), isPending: false }),
  useRequestAccountDeletion: () => ({
    mutate: vi.fn(),
    isPending: false,
    reset: vi.fn(),
  }),
  useCancelAccountDeletion: () => ({ mutate: vi.fn(), isPending: false }),
  useActiveSessions: () => ({
    data: { sessions: [], new_session_at: null },
    isLoading: false,
    error: null,
  }),
  useCloseSession: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useCloseOtherSessions: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useAcknowledgeNewSession: () => ({ mutate: vi.fn(), isPending: false }),
  // F1 / T4 additions.
  useLocalProfileStatus: () => statusMock(),
  useLocalProfileLock: () => ({
    mutate: lockState.mutate,
    isPending: lockState.isPending,
  }),
  LOCAL_PASSWORD_MIN_LENGTH: 8,
}));

vi.mock("../queries/useAppConfig", () => ({
  useAppConfig: () => useAppConfigMock(),
  emailFlowsEnabled: () => true,
}));

vi.mock("../queries/useActivity", () => ({
  useActivity: () => ({
    data: {
      events: [],
      month: { chats: 0, analyses: 0, files: 0, rows: 0, archives: 0 },
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => vi.fn() };
});

describe("ProfileView local lock (F1 / T4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lockState.mutate.mockReset();
    lockState.isPending = false;
    useMeMock.mockReturnValue({
      data: { id: 1, email: null, name: "Ana", pending_deletion_at: null },
      isLoading: false,
      error: null,
    });
    useAppConfigMock.mockReturnValue({ data: { mode: "local" }, isError: false });
    statusMock.mockReturnValue({
      data: { exists: true, hosted_accounts: false, locked: false },
      isLoading: false,
      error: null,
    });
  });

  it("shows the unlock section in local mode", () => {
    renderWithProviders(<ProfileView />);

    expect(
      screen.getByRole("heading", { name: "Bloqueo del perfil" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Activar bloqueo" })).toBeTruthy();
  });

  it("hides the unlock section outside local mode", () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "hosted" }, isError: false });

    renderWithProviders(<ProfileView />);

    expect(
      screen.queryByRole("heading", { name: "Bloqueo del perfil" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Activar bloqueo" })).toBeNull();
  });

  it("calls the lock route and shows the one-time key with its warning", async () => {
    lockState.mutate.mockImplementation(
      (_body: unknown, options: { onSuccess: (data: { rescue_key: string }) => void }) =>
        options.onSuccess({ rescue_key: "RESCATE-123" }),
    );

    renderWithProviders(<ProfileView />);
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "secreto123" },
    });
    fireEvent.change(screen.getByLabelText("Repite la contraseña"), {
      target: { value: "secreto123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Activar bloqueo" }));

    await waitFor(() =>
      expect(lockState.mutate).toHaveBeenCalledWith(
        { password: "secreto123" },
        expect.anything(),
      ),
    );
    // The key is revealed once and never stored; the form is replaced.
    expect(screen.getByText("RESCATE-123")).toBeTruthy();
    expect(
      screen.getByText(/Guárdala en un lugar seguro. No se vuelve a mostrar./i),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Activar bloqueo" })).toBeNull();
  });

  it("shows the locked state and no form when the profile is already locked", () => {
    statusMock.mockReturnValue({
      data: { exists: true, hosted_accounts: false, locked: true },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ProfileView />);

    expect(screen.getByText("Tu perfil está bloqueado con una contraseña.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Activar bloqueo" })).toBeNull();
  });
});
