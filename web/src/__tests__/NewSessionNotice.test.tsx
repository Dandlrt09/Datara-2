/* Tests for the new-session notice (T2.4).
 *
 * The banner is derived from the same `useActiveSessions` payload as the card:
 * it shows only while the server reports an unseen `new_session_at`, and
 * `Entendido` marks it seen through the acknowledge mutation.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { PreferencesProvider } from "../lib/preferences";
import NewSessionNotice from "../components/NewSessionNotice";

const { activeSessionsMock, acknowledgeMock, settingsMock } = vi.hoisted(() => ({
  activeSessionsMock: vi.fn(),
  acknowledgeMock: vi.fn(),
  settingsMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useActiveSessions: () => activeSessionsMock(),
  useAcknowledgeNewSession: () => acknowledgeMock(),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => settingsMock(),
}));

function renderNotice(newSessionAt: string | null) {
  activeSessionsMock.mockReturnValue({
    data: { sessions: [], new_session_at: newSessionAt },
    isLoading: false,
    error: null,
  });
  return renderWithProviders(
    <PreferencesProvider>
      <NewSessionNotice />
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
  acknowledgeMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe("NewSessionNotice", () => {
  it("renders nothing when there is no unseen session", () => {
    renderNotice(null);

    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByText("Entró una nueva sesión")).toBeNull();
  });

  it("shows the notice and the session date when there is one", () => {
    renderNotice("2026-10-26 21:09:18");

    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText("Entró una nueva sesión")).toBeTruthy();
    expect(
      screen.getByText(
        "Se abrió una sesión el 26/10/2026 desde otro navegador. Si no fuiste vos, cambiá tu contraseña y cerrá las demás.",
      ),
    ).toBeTruthy();
  });

  it("acknowledges the notice from the Entendido button", () => {
    const mutate = vi.fn();
    acknowledgeMock.mockReturnValue({ mutate, isPending: false });
    renderNotice("2026-10-26 21:09:18");

    fireEvent.click(screen.getByRole("button", { name: "Entendido" }));

    expect(mutate).toHaveBeenCalledTimes(1);
  });
});
