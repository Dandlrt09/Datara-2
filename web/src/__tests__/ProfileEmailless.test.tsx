import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";

/* F1 / T5: a local profile has no address at all (`email: null`), so the
 * sidebar and the Perfil card must show a neutral label where the address used
 * to be, and the string "null" must never reach the screen. The hooks are
 * mocked like the neighbouring screen tests, and the real components render so
 * the copy itself is what is under test. */
const { useMeMock, useAppConfigMock, statusMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useAppConfigMock: vi.fn(),
  statusMock: vi.fn(),
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
  useLocalProfileStatus: () => statusMock(),
  useLocalProfileLock: () => ({ mutate: vi.fn(), isPending: false }),
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

vi.mock("../queries/useSettings", () => ({
  useSettings: () => ({ data: undefined, isLoading: false, error: null }),
  useUpdateSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// AppShell renders the real ProfileView; this suite mounts it on /app/chat, so
// only the routes it can actually reach have to be stubbed out.
vi.mock("../routes/ChatView", () => ({
  default: () => <div data-testid="chat-view">chat</div>,
}));
vi.mock("../routes/FilesView", () => ({ default: () => <div>files</div> }));
vi.mock("../routes/SettingsView", () => ({ default: () => <div>settings</div> }));
vi.mock("../routes/ArchiveList", () => ({ default: () => <div>archives</div> }));

import ProfileView from "../routes/ProfileView";
import AppShell from "../routes/AppShell";

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

function mockLocalProfile() {
  useAppConfigMock.mockReturnValue({ data: { mode: "local" }, isError: false });
  statusMock.mockReturnValue({
    data: { exists: true, hosted_accounts: false, locked: false },
    isLoading: false,
    error: null,
  });
}

describe("Perfil without an address (F1 / T5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalProfile();
  });

  it("shows the name and a neutral label instead of the missing address", () => {
    useMeMock.mockReturnValue(localUser());

    renderWithProviders(<ProfileView />);

    expect(screen.getAllByText("Ana").length).toBeGreaterThan(0);
    // Both places that used to show the email (the avatar block and the
    // account row) now show the neutral label.
    expect(screen.getAllByText("Perfil local")).toHaveLength(2);
    // The absent address must never surface as the literal "null".
    expect(document.body.textContent).not.toContain("null");
  });

  it("leaves a hosted account byte-for-byte unchanged", () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "hosted" }, isError: false });
    useMeMock.mockReturnValue(hostedUser());

    renderWithProviders(<ProfileView />);

    expect(screen.getAllByText("dan@datara.ai")).toHaveLength(2);
    expect(screen.getByText("Correo electrónico")).toBeTruthy();
    expect(screen.queryByText("Perfil local")).toBeNull();
  });
});

describe("Sidebar without an address (F1 / T5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalProfile();
  });

  it("shows the neutral label where the address used to be", () => {
    useMeMock.mockReturnValue(localUser());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    expect(screen.getByText("Ana")).toBeTruthy();
    expect(screen.getByText("Perfil local")).toBeTruthy();
    expect(document.body.textContent).not.toContain("null");
  });

  it("leaves a hosted sidebar byte-for-byte unchanged", () => {
    useMeMock.mockReturnValue(hostedUser());

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    expect(screen.getByText("dan@datara.ai")).toBeTruthy();
    expect(screen.queryByText("Perfil local")).toBeNull();
  });
});
