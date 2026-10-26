/* Tests for the active-sessions card (T2.4).
 *
 * The card is driven through the real component with the `useAuth` session
 * hooks and the `useSettings` query stubbed at their usual seams (the same way
 * PreferencesCard/ProfileView tests do it). Every assertion checks what the
 * user sees: the browser label, the current-session badge, the last-activity
 * line and the two closing flows.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { PreferencesProvider } from "../lib/preferences";
import ActiveSessionsCard from "../components/ActiveSessionsCard";
import type { ActiveSession } from "../queries/useAuth";

const {
  activeSessionsMock,
  closeSessionMock,
  closeOtherSessionsMock,
  settingsMock,
} = vi.hoisted(() => ({
  activeSessionsMock: vi.fn(),
  closeSessionMock: vi.fn(),
  closeOtherSessionsMock: vi.fn(),
  settingsMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useActiveSessions: () => activeSessionsMock(),
  useCloseSession: () => closeSessionMock(),
  useCloseOtherSessions: () => closeOtherSessionsMock(),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => settingsMock(),
}));

const CHROME_WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36";
const FIREFOX_LINUX =
  "Mozilla/5.0 (X11; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0";

/** SQLite's zone-less UTC shape (`datetime('now')`). */
function sqliteUtc(date: Date): string {
  return date.toISOString().slice(0, 19).replace("T", " ");
}

function makeSession(overrides: Partial<ActiveSession> = {}): ActiveSession {
  const now = new Date();
  return {
    id: 1,
    user_agent: CHROME_WINDOWS,
    created_at: sqliteUtc(now),
    last_seen_at: sqliteUtc(now),
    is_current: false,
    ...overrides,
  };
}

function renderCard(sessions: ActiveSession[]) {
  activeSessionsMock.mockReturnValue({
    data: { sessions, new_session_at: null },
    isLoading: false,
    error: null,
  });
  return renderWithProviders(
    <PreferencesProvider>
      <ActiveSessionsCard />
    </PreferencesProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  settingsMock.mockReturnValue({
    data: { user_id: 1, date_format: "absolute" },
    isLoading: false,
    error: null,
  });
  closeSessionMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  });
  closeOtherSessionsMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  });
});

describe("ActiveSessionsCard", () => {
  it("renders one row per session with its browser label", () => {
    renderCard([
      makeSession({ id: 1, is_current: true }),
      makeSession({ id: 2, user_agent: FIREFOX_LINUX }),
    ]);

    expect(screen.getByText("Chrome en Windows")).toBeTruthy();
    expect(screen.getByText("Firefox en Linux")).toBeTruthy();
  });

  it("badges the current session and does not offer to close it", () => {
    renderCard([makeSession({ id: 1, is_current: true })]);

    expect(screen.getByText("Esta sesión")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Cerrar la sesión en Chrome en Windows" }),
    ).toBeNull();
  });

  it("names an unknown user agent as a generic device", () => {
    renderCard([makeSession({ id: 2, user_agent: null })]);

    expect(screen.getByText("Dispositivo desconocido")).toBeTruthy();
  });

  it("closes a non-current session with its id", () => {
    const mutate = vi.fn();
    closeSessionMock.mockReturnValue({ mutate, isPending: false, isError: false });
    renderCard([
      makeSession({ id: 1, is_current: true }),
      makeSession({ id: 2, user_agent: FIREFOX_LINUX }),
    ]);

    fireEvent.click(
      screen.getByRole("button", { name: "Cerrar la sesión en Firefox en Linux" }),
    );

    expect(mutate).toHaveBeenCalledWith(2);
  });

  it("disables 'Cerrar todas las demás' when there are no other sessions", () => {
    renderCard([makeSession({ id: 1, is_current: true })]);

    expect(
      (screen.getByRole("button", { name: "Cerrar todas las demás" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("closes every other session when there is one", () => {
    const mutate = vi.fn();
    closeOtherSessionsMock.mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
    });
    renderCard([
      makeSession({ id: 1, is_current: true }),
      makeSession({ id: 2, user_agent: FIREFOX_LINUX }),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar todas las demás" }));

    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it("renders the last-activity line through the date preference", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1, date_format: "relative" },
      isLoading: false,
      error: null,
    });
    renderCard([makeSession({ id: 1, is_current: true })]);

    expect(screen.getByText("Última actividad: hace un momento")).toBeTruthy();
  });
});
