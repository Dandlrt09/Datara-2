import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { DELETION_SCHEDULED_NOTICE } from "../components/DeleteAccountDialog";

/* F1 / T1 (S1): local mode has no email login, so signing out must return to
 * the local landing -- the password screen when the profile is locked,
 * otherwise whatever `/first-run` does. Hosted mode keeps the email login. */
const {
  useMeMock,
  configMock,
  statusMock,
  logoutMock,
  navigateMock,
  deleteMutateMock,
} = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  configMock: vi.fn(),
  statusMock: vi.fn(),
  logoutMock: vi.fn(),
  navigateMock: vi.fn(),
  deleteMutateMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLogout: () => ({ mutateAsync: logoutMock, isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useUpdateName: () => ({ mutate: vi.fn(), isPending: false }),
  useRequestAccountDeletion: () => ({
    mutate: deleteMutateMock,
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
  useLocalProfileStatus: () => statusMock(),
  useLocalProfileLock: () => ({ mutate: vi.fn(), isPending: false }),
  LOCAL_PASSWORD_MIN_LENGTH: 8,
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

vi.mock("../queries/useAppConfig", async () => {
  const actual = await vi.importActual<typeof import("../queries/useAppConfig")>(
    "../queries/useAppConfig",
  );
  return { ...actual, useAppConfig: () => configMock() };
});

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import ProfileView from "../routes/ProfileView";
import AppShell from "../routes/AppShell";
import { PendingDeletionScreen } from "../components/PendingDeletionScreen";

function localUser() {
  return {
    data: { id: 1, email: null, name: "Ana", pending_deletion_at: null },
    isLoading: false,
    error: null,
  };
}

function hostedUser() {
  return {
    data: {
      id: 1,
      email: "dan@datara.ai",
      name: null,
      pending_deletion_at: null,
    },
    isLoading: false,
    error: null,
  };
}

function localConfig() {
  return { data: { mode: "local" }, isError: false };
}

function hostedConfig() {
  return { data: { mode: "hosted" }, isError: false };
}

function unlockedStatus() {
  return {
    data: {
      exists: true,
      hosted_accounts: false,
      locked: false,
      lock_step_pending: false,
    },
    isLoading: false,
    error: null,
  };
}

describe("ProfileView logout landing (F1 / T1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    logoutMock.mockResolvedValue(undefined);
    statusMock.mockReturnValue(unlockedStatus());
  });

  it("lands on the local landing in local mode", async () => {
    configMock.mockReturnValue(localConfig());
    useMeMock.mockReturnValue(localUser());

    renderWithProviders(<ProfileView />);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledTimes(1));
    expect(navigateMock).toHaveBeenCalledWith("/first-run", { replace: true });
  });

  it("keeps landing on /login in hosted mode", async () => {
    configMock.mockReturnValue(hostedConfig());
    useMeMock.mockReturnValue(hostedUser());

    renderWithProviders(<ProfileView />);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledTimes(1));
    expect(navigateMock).toHaveBeenCalledWith("/login", { replace: true });
  });
});

describe("ProfileView one password story (F1 / T2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("hides the generic change-password row in local mode without a lock", () => {
    configMock.mockReturnValue(localConfig());
    useMeMock.mockReturnValue(localUser());
    statusMock.mockReturnValue(unlockedStatus());

    renderWithProviders(<ProfileView />);

    // The profile has no password, so the generic form cannot work: the lock
    // section owns it instead.
    expect(screen.queryByRole("button", { name: "Cambiar" })).toBeNull();
    expect(
      screen.getByRole("heading", { name: "Bloqueo del perfil" }),
    ).toBeTruthy();
  });

  it("keeps the row when the local lock is on", () => {
    configMock.mockReturnValue(localConfig());
    useMeMock.mockReturnValue(localUser());
    statusMock.mockReturnValue({
      data: {
        exists: true,
        hosted_accounts: false,
        locked: true,
        lock_step_pending: false,
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<ProfileView />);

    expect(screen.getByRole("button", { name: "Cambiar" })).toBeTruthy();
  });
});

/* F1 / T4: scheduling the deletion closes every session server-side, so the
 * app leaves the authenticated shell. Hosted explains how to cancel on the
 * email login; local mode has no email login, so it must return to the local
 * landing -- the pending-deletion screen repeats the deadline as soon as the
 * profile is unlocked. */
function openAndConfirmDeletion() {
  fireEvent.click(screen.getByRole("button", { name: "Eliminar mi cuenta" }));
  const dialog = screen.getByRole("dialog", { name: "Eliminar cuenta" });
  fireEvent.change(
    within(dialog).getByLabelText("Escribe ELIMINAR para confirmar"),
    { target: { value: "ELIMINAR" } },
  );
  fireEvent.change(within(dialog).getByLabelText("Contraseña actual"), {
    target: { value: "una-clave-larga" },
  });
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Eliminar mi cuenta" }),
  );
}

describe("ProfileView deletion landing (F1 / T4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    statusMock.mockReturnValue(unlockedStatus());
    // The hook reports success the way react-query does: through the options
    // the dialog passes to mutate.
    deleteMutateMock.mockImplementation(
      (_vars: unknown, options?: { onSuccess?: () => void }) =>
        options?.onSuccess?.(),
    );
  });

  it("lands on the local landing in local mode, never the email login", () => {
    configMock.mockReturnValue(localConfig());
    useMeMock.mockReturnValue(localUser());

    renderWithProviders(<ProfileView />);
    openAndConfirmDeletion();

    expect(navigateMock).toHaveBeenCalledWith("/first-run", { replace: true });
    expect(navigateMock).not.toHaveBeenCalledWith(
      "/login",
      expect.anything(),
    );
  });

  it("keeps the login notice in hosted mode", () => {
    configMock.mockReturnValue(hostedConfig());
    useMeMock.mockReturnValue(hostedUser());

    renderWithProviders(<ProfileView />);
    openAndConfirmDeletion();

    expect(navigateMock).toHaveBeenCalledWith("/login", {
      replace: true,
      state: { notice: DELETION_SCHEDULED_NOTICE },
    });
  });
});

describe("PendingDeletionScreen logout landing (F1 / T4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    logoutMock.mockResolvedValue(undefined);
  });

  it("lands on the local landing in local mode", async () => {
    configMock.mockReturnValue(localConfig());

    renderWithProviders(<PendingDeletionScreen deadline="2099-01-01 00:00:00" />);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledTimes(1));
    expect(navigateMock).toHaveBeenCalledWith("/first-run", { replace: true });
  });

  it("keeps landing on /login in hosted mode", async () => {
    configMock.mockReturnValue(hostedConfig());

    renderWithProviders(<PendingDeletionScreen deadline="2099-01-01 00:00:00" />);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledTimes(1));
    expect(navigateMock).toHaveBeenCalledWith("/login", { replace: true });
  });
});

describe("AppShell lost-session landing (F1 / T1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMeMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("no session"),
    });
  });

  it("lands on the local landing in local mode", async () => {
    configMock.mockReturnValue(localConfig());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/first-run", { replace: true }),
    );
  });

  it("keeps landing on /login in hosted mode", async () => {
    configMock.mockReturnValue(hostedConfig());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/login", { replace: true }),
    );
  });
});
