import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ProfileView from "../routes/ProfileView";
import { NAME_UPDATED_NOTICE } from "../components/NameDialog";

const { useMeMock, logoutMock, navigateMock, updateNameState } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  logoutMock: vi.fn(),
  navigateMock: vi.fn(),
  updateNameState: { mutate: vi.fn(), pending: false },
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLogout: () => ({ mutateAsync: logoutMock, isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useUpdateName: () => ({
    mutate: updateNameState.mutate,
    isPending: updateNameState.pending,
  }),
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
  return { ...actual, useNavigate: () => navigateMock };
});

describe("ProfileView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    logoutMock.mockResolvedValue(undefined);
    updateNameState.pending = false;
    updateNameState.mutate.mockReset();
    useMeMock.mockReturnValue({
      data: { id: 1, email: "dan@datara.ai", name: null },
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

    // The derived name shows twice now: the avatar block heading and the
    // Nombre row value built from the same resolved name (T1/D6/D7).
    expect(screen.getAllByText("dan")).toHaveLength(2);
    expect(screen.getByText("D")).toBeTruthy();
    expect(screen.getByText("Nombre")).toBeTruthy();
  });

  it("shows the chosen name instead of the email local part", () => {
    useMeMock.mockReturnValue({
      data: { id: 1, email: "dan@datara.ai", name: "Daniel Del Rio" },
      isLoading: false,
      error: null,
    });
    renderWithProviders(<ProfileView />);

    expect(screen.getAllByText("Daniel Del Rio")).toHaveLength(2);
    // The avatar letter follows the chosen name too.
    expect(screen.getByText("D")).toBeTruthy();
    expect(screen.queryByText("dan")).toBeNull();
  });

  it("lets the longest allowed name wrap instead of widening the card", () => {
    // Live finding (L11): with `overflowWrap` missing, a long name pushed the
    // heading past the card border. The rule is that no allowed name can widen
    // the layout, so the heading must break inside a word.
    useMeMock.mockReturnValue({
      data: { id: 1, email: "dan@datara.ai", name: "N".repeat(50) },
      isLoading: false,
      error: null,
    });
    renderWithProviders(<ProfileView />);

    // The card also renders other level-2 headings ("Sesiones activas", …),
    // so the name heading is picked by its text to stay unambiguous.
    const heading = screen.getByRole("heading", {
      level: 2,
      name: "N".repeat(50),
    });

    expect(heading.style.overflowWrap).toBe("anywhere");
  });

  it("opens the name dialog from the Nombre row", () => {
    renderWithProviders(<ProfileView />);

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));

    expect(screen.getByRole("dialog", { name: "Editar nombre" })).toBeTruthy();
  });

  it("closes the name dialog and shows the notice once it is saved", async () => {
    updateNameState.mutate.mockImplementation(
      (_vars: unknown, options: { onSuccess: () => void }) => options.onSuccess(),
    );
    renderWithProviders(<ProfileView />);

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: "Daniel Del Rio" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status").textContent).toBe(NAME_UPDATED_NOTICE);
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
