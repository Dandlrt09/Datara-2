import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ProfileView from "../routes/ProfileView";

const { useMeMock, logoutMock, navigateMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  logoutMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLogout: () => ({ mutateAsync: logoutMock, isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useRequestAccountDeletion: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useCancelAccountDeletion: () => ({ mutate: vi.fn(), isPending: false }),
  useActiveSessions: () => ({
    data: { sessions: [], new_session_at: null },
    isLoading: false,
    error: null,
  }),
  useCloseSession: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useCloseOtherSessions: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useAcknowledgeNewSession: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

describe("ProfileView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    logoutMock.mockResolvedValue(undefined);
    useMeMock.mockReturnValue({
      data: { id: 1, email: "dan@datara.ai" },
      isLoading: false,
      error: null,
    });
  });

  it("renders the heading and the read-only email", () => {
    renderWithProviders(<ProfileView />);

    expect(screen.getByRole("heading", { name: "Perfil" })).toBeTruthy();
    // The email is shown in the avatar block and in the read-only row, never
    // as an editable field.
    expect(screen.getAllByText("dan@datara.ai").length).toBeGreaterThan(0);
    expect(screen.getByText("Correo electrónico")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("derives the display name and avatar letter from the email", () => {
    renderWithProviders(<ProfileView />);

    expect(screen.getByText("dan")).toBeTruthy();
    expect(screen.getByText("D")).toBeTruthy();
  });

  it("opens the change-password dialog from the Cambiar button", () => {
    renderWithProviders(<ProfileView />);

    fireEvent.click(screen.getByRole("button", { name: "Cambiar" }));

    expect(screen.getByRole("dialog", { name: "Cambiar contraseña" })).toBeTruthy();
  });

  it("logs out and navigates to /login from the Sesión card", async () => {
    renderWithProviders(<ProfileView />);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledTimes(1));
    expect(navigateMock).toHaveBeenCalledWith("/login", { replace: true });
  });

  it("opens the delete-account dialog from the danger zone", () => {
    renderWithProviders(<ProfileView />);

    fireEvent.click(screen.getByRole("button", { name: "Eliminar mi cuenta" }));

    expect(screen.getByRole("dialog", { name: "Eliminar cuenta" })).toBeTruthy();
  });

  it("shows a loading state while the user is unknown", () => {
    useMeMock.mockReturnValue({ data: undefined, isLoading: true, error: null });
    renderWithProviders(<ProfileView />);

    expect(screen.getByText("Cargando perfil…")).toBeTruthy();
  });

  it("renders nothing instead of crashing when there is no user", () => {
    useMeMock.mockReturnValue({ data: undefined, isLoading: false, error: null });
    renderWithProviders(<ProfileView />);

    expect(screen.queryByRole("heading", { name: "Perfil" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cerrar sesión" })).toBeNull();
  });
});
