import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  PendingDeletionScreen,
  PENDING_DELETION_HEADING,
} from "../components/PendingDeletionScreen";
import { PreferencesProvider } from "../lib/preferences";

const { cancelMock, logoutMock, navigateMock, settingsState } = vi.hoisted(() => ({
  cancelMock: vi.fn(),
  logoutMock: vi.fn(),
  navigateMock: vi.fn(),
  settingsState: { data: undefined as unknown },
}));

vi.mock("../queries/useAuth", () => ({
  useCancelAccountDeletion: () => ({
    mutate: cancelMock,
    isPending: false,
    error: null,
  }),
  useLogout: () => ({ mutateAsync: logoutMock, isPending: false }),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => ({ data: settingsState.data }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

function renderScreen(deadline = "2099-01-01 00:00:00", withPreferences = false) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const screen = (
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        {withPreferences ? (
          <PreferencesProvider>
            <PendingDeletionScreen deadline={deadline} />
          </PreferencesProvider>
        ) : (
          <PendingDeletionScreen deadline={deadline} />
        )}
      </QueryClientProvider>
    </MemoryRouter>
  );
  return render(screen);
}

describe("PendingDeletionScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsState.data = undefined;
    logoutMock.mockResolvedValue(undefined);
  });

  it("states that the account will be deleted and blocks the app", () => {
    renderScreen();

    expect(
      screen.getByRole("heading", { name: PENDING_DELETION_HEADING }),
    ).toBeTruthy();
    expect(screen.getByText(/Eliminación programada/)).toBeTruthy();
    expect(screen.getByText(/no puedes usar la app/)).toBeTruthy();
  });

  it("renders the absolute deadline when that preference is set", () => {
    settingsState.data = { date_format: "absolute" };
    // The stored deadline is UTC (that is the shape `GET /api/auth/me` returns)
    // and the screen shows it in the reader's own zone, so the expectation is
    // derived from the same instant instead of hardcoded: in a zone west of
    // Greenwich this instant is still 31/12/2098 locally.
    const deadlineUtc = new Date("2099-01-01T00:00:00Z");
    const expected = new RegExp(
      `${String(deadlineUtc.getDate()).padStart(2, "0")}/${String(
        deadlineUtc.getMonth() + 1,
      ).padStart(2, "0")}/${deadlineUtc.getFullYear()}`,
    );

    renderScreen("2099-01-01 00:00:00", true);

    expect(screen.getByText(expected)).toBeTruthy();
  });

  it("cancels the deletion from the primary action", () => {
    renderScreen();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar el borrado" }));

    expect(cancelMock).toHaveBeenCalledTimes(1);
  });

  it("logs out and lands on /login from the secondary action", async () => {
    renderScreen();

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledTimes(1));
    expect(navigateMock).toHaveBeenCalledWith("/login", { replace: true });
  });
});
