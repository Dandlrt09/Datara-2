import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";

/* F1 / T3: the optional lock is offered on the onboarding path. The screen and
 * the gate talk to the network through the shared hooks, so these tests mock
 * `useAuth` (like `ProfileLock.test.tsx`) and let the real components render:
 * the offer, the one-time rescue key, the explicit decline, and the redirect
 * that puts the step on the path are what is under test. */
const { useMeMock, statusMock, lockState, declineState } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  statusMock: vi.fn(),
  lockState: { mutate: vi.fn(), isPending: false },
  declineState: { mutate: vi.fn(), isPending: false },
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLocalProfileStatus: () => statusMock(),
  useLocalProfileLock: () => ({
    mutate: lockState.mutate,
    isPending: lockState.isPending,
  }),
  useDeclineLockStep: () => ({
    mutate: declineState.mutate,
    isPending: declineState.isPending,
  }),
  LOCAL_PASSWORD_MIN_LENGTH: 8,
}));

import LockStepScreen from "../routes/LockStepScreen";
import AppShell from "../routes/AppShell";

function localUser() {
  return {
    data: { id: 1, email: null, name: "Ana", pending_deletion_at: null },
    isLoading: false,
    error: null,
  };
}

function pendingStatus() {
  return {
    data: {
      exists: true,
      hosted_accounts: false,
      locked: false,
      lock_step_pending: true,
    },
    isLoading: false,
    error: null,
  };
}

/** A status read that failed at mount: no data, an error, and a retry hook.
 * This is what a single 500 used to turn into a released app. */
function errorStatus(refetch: () => void = () => {}) {
  return {
    data: undefined,
    isLoading: false,
    error: new Error("status unavailable"),
    isError: true,
    refetch,
  };
}

describe("LockStepScreen (F1 / T3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lockState.mutate.mockReset();
    lockState.isPending = false;
    declineState.mutate.mockReset();
    declineState.isPending = false;
  });

  it("offers the optional lock before the API-key setup", () => {
    renderWithProviders(<LockStepScreen />);

    expect(
      screen.getByRole("heading", { name: "Protege tu perfil" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Activar el bloqueo" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ahora no" })).toBeTruthy();
  });

  it("activates the lock and shows the rescue key exactly once", async () => {
    lockState.mutate.mockImplementation(
      (
        _body: unknown,
        options: { onSuccess: (data: { rescue_key: string }) => void },
      ) => options.onSuccess({ rescue_key: "RESCATE-123" }),
    );
    const onAnswered = vi.fn();

    renderWithProviders(<LockStepScreen onAnswered={onAnswered} />);
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "secreto123" },
    });
    fireEvent.change(screen.getByLabelText("Repite la contraseña"), {
      target: { value: "secreto123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Activar el bloqueo" }));

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
    expect(
      screen.queryByRole("button", { name: "Activar el bloqueo" }),
    ).toBeNull();
    // The gate is not released until the analyst keeps the key.
    expect(onAnswered).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    expect(onAnswered).toHaveBeenCalledTimes(1);
  });

  it("declines through the decline route and releases the gate", async () => {
    declineState.mutate.mockImplementation(
      (_body: unknown, options: { onSuccess: () => void }) =>
        options.onSuccess(),
    );
    const onAnswered = vi.fn();

    renderWithProviders(<LockStepScreen onAnswered={onAnswered} />);
    fireEvent.click(screen.getByRole("button", { name: "Ahora no" }));

    await waitFor(() =>
      expect(declineState.mutate).toHaveBeenCalledWith(
        undefined,
        expect.anything(),
      ),
    );
    expect(onAnswered).toHaveBeenCalledTimes(1);
  });
});

describe("LockStep gate (F1 / T3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lockState.mutate.mockReset();
    declineState.mutate.mockReset();
  });

  it("sends a signed-in local analyst with a pending step to the lock screen", async () => {
    useMeMock.mockReturnValue(localUser());
    statusMock.mockReturnValue(pendingStatus());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    expect(
      await screen.findByRole("heading", { name: "Protege tu perfil" }),
    ).toBeTruthy();
    // The app itself is not reachable while the step is pending.
    expect(screen.queryByText("Datara")).toBeNull();
  });

  it("releases the gate once the step is answered", async () => {
    useMeMock.mockReturnValue(localUser());
    statusMock.mockReturnValue(pendingStatus());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });
    await screen.findByRole("heading", { name: "Protege tu perfil" });

    declineState.mutate.mockImplementation(
      (_body: unknown, options: { onSuccess: () => void }) =>
        options.onSuccess(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Ahora no" }));

    // The status query is still stale (pending), but the gate released on the
    // answer, so the app is reachable instead of showing the screen forever.
    expect(await screen.findByText("Datara")).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Protege tu perfil" }),
    ).toBeNull();
  });

  it("keeps the app unreachable when the status query fails at mount", async () => {
    useMeMock.mockReturnValue(localUser());
    statusMock.mockReturnValue(errorStatus());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    // A failed status read must not release the mandatory step: the panel
    // explains the failure and offers a retry, and the app stays out of reach.
    expect(
      await screen.findByText(/no pudimos comprobar/i),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeTruthy();
    expect(screen.queryByText("Datara")).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Protege tu perfil" }),
    ).toBeNull();
  });

  it("resolves the gate after the failed status read is retried", async () => {
    useMeMock.mockReturnValue(localUser());
    const refetch = vi.fn(() => {
      statusMock.mockReturnValue(pendingStatus());
    });
    statusMock.mockReturnValue(errorStatus(refetch));

    const { rerender } = renderWithProviders(<AppShell />, {
      route: "/app/chat",
      path: "/app/*",
    });
    await screen.findByRole("button", { name: "Reintentar" });

    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(refetch).toHaveBeenCalledTimes(1);

    // The refetch succeeded: the status now reports the step pending, so the
    // gate resolves to the step screen instead of the app.
    rerender(<AppShell />);
    expect(
      await screen.findByRole("heading", { name: "Protege tu perfil" }),
    ).toBeTruthy();
    expect(screen.queryByText("Datara")).toBeNull();
  });
});
