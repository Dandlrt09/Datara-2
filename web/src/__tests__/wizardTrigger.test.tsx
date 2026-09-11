import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import AppShell from "../routes/AppShell";
import { useWizardStore } from "../stores/useWizardStore";
import { useChatStore } from "../stores/useChatStore";
import { clearWizardFlags } from "../lib/wizardStorage";

// Mock route components
vi.mock("../routes/ChatView", () => ({
  default: () => <div data-testid="chat-view">Chat View</div>,
}));

vi.mock("../routes/FilesView", () => ({
  default: () => <div data-testid="files-view">Files View</div>,
}));

vi.mock("../routes/SettingsView", () => ({
  default: () => <div data-testid="settings-view">Settings View</div>,
}));

vi.mock("../routes/ArchiveList", () => ({
  default: () => <div data-testid="archive-view">Archive View</div>,
}));

// Mock auth
vi.mock("../queries/useAuth", () => ({
  useMe: () => ({
    data: { id: 1, email: "test@test.com" },
    isLoading: false,
    error: null,
  }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// Hoisted mocks for query hooks
const { useSessionsMock, useFilesGlobalMock } = vi.hoisted(() => ({
  useSessionsMock: vi.fn(),
  useFilesGlobalMock: vi.fn(),
}));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => useSessionsMock(),
}));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => useFilesGlobalMock(),
}));

// Mock SSE
vi.mock("../lib/useSessionEvents", () => ({
  useSessionEvents: () => {},
}));

function renderAppShell(initialRoute = "/app/chat") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/app/*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  return { queryClient };
}

describe("AppShell wizard trigger (wizardTrigger.test.tsx)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearWizardFlags();
    
    // Reset store state
    useWizardStore.setState({
      open: false,
      engaged: false,
      manual: false,
      dismissed: false,
    });

    // Reset chat store
    useChatStore.setState({
      activeSessionId: null,
      streamingText: "",
      appendStreamingText: vi.fn(),
      clearStreamingText: vi.fn(),
      pendingArtifacts: null,
      setPendingArtifacts: vi.fn(),
      isStreaming: false,
      setStreaming: vi.fn(),
    });

    // Default mock: fresh user (0 sessions, 0 files, queries resolved)
    useSessionsMock.mockReturnValue({
      data: [],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });

    useFilesGlobalMock.mockReturnValue({
      data: [],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("auto-opens the wizard for a fresh user (0 sessions, 0 files, queries resolved)", async () => {
    renderAppShell();

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /first-run wizard/i })).toBeTruthy();
    });
  });

  it("does NOT open wizard when user has 1+ sessions", async () => {
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Test Session" }],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });

    renderAppShell();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });
  });

  it("does NOT open wizard when user has 1+ files", async () => {
    useFilesGlobalMock.mockReturnValue({
      data: [{ id: 1, filename: "test.csv", format: "csv", size_bytes: 1024, session_title: null }],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });

    renderAppShell();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });
  });

  it("does NOT open wizard while sessions query is loading (no flash)", async () => {
    useSessionsMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      isError: false,
    });

    renderAppShell();

    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("does NOT open wizard while files query is loading (no flash)", async () => {
    useFilesGlobalMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      isError: false,
    });

    renderAppShell();

    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("does NOT open wizard while streaming is active", async () => {
    useChatStore.setState({ isStreaming: true });

    renderAppShell();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });
  });

  it("auto-closes wizard when sessions cache flips non-empty while un-engaged", async () => {
    // Start with 0 sessions, wizard should open
    renderAppShell();

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /first-run wizard/i })).toBeTruthy();
    });

    // Wizard is not engaged yet, simulate sessions becoming non-empty
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "New Session" }],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });

    // Re-render with updated mocks
    renderAppShell();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });
  });

  it("does NOT auto-close wizard when engaged (even if trigger conditions change)", async () => {
    // Start with wizard open
    renderAppShell();

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /first-run wizard/i })).toBeTruthy();
    });

    // Mark wizard as engaged (user clicked "Get started" or dropped a file)
    useWizardStore.setState({ engaged: true });

    // Simulate sessions becoming non-empty
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "New Session" }],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });

    // Re-render - wizard should stay open because it's engaged
    renderAppShell();

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /first-run wizard/i })).toBeTruthy();
    });
  });

  it("does NOT auto-close wizard when opened manually (even if trigger conditions change)", async () => {
    // Simulate manual open (e.g., from ChatView empty state)
    useWizardStore.setState({ open: true, manual: true });

    // User has sessions, but wizard was opened manually
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Existing Session" }],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });

    renderAppShell();

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /first-run wizard/i })).toBeTruthy();
    });
  });

  it("persists skipped state across remounts", async () => {
    // First render, wizard opens
    renderAppShell();

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /first-run wizard/i })).toBeTruthy();
    });

    // Click skip
    fireEvent.click(screen.getByText("Skip"));

    // Wizard should close
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });

    // Remount - wizard should NOT open because skipped flag is persisted
    renderAppShell();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });
  });

  it("does NOT open when wizard was previously completed", async () => {
    // Simulate completed wizard (from localStorage or store)
    useWizardStore.setState({ dismissed: true });

    renderAppShell();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
    });
  });
});