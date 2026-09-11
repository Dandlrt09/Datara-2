import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import AppShell from "../routes/AppShell";
import { useWizardStore } from "../stores/useWizardStore";
import { useChatStore } from "../stores/useChatStore";
import { clearWizardFlags } from "../lib/wizardStorage";

// Mocks
vi.mock("../routes/ChatView", () => ({ default: () => <div>Chat</div> }));
vi.mock("../routes/FilesView", () => ({ default: () => <div>Files</div> }));
vi.mock("../routes/SettingsView", () => ({ default: () => <div>Settings</div> }));
vi.mock("../routes/ArchiveList", () => ({ default: () => <div>Archives</div> }));

vi.mock("../queries/useAuth", () => ({
  useMe: () => ({ data: { id: 1, email: "test@test.com" }, isLoading: false, error: null }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const { useSessionsMock, useFilesGlobalMock } = vi.hoisted(() => ({
  useSessionsMock: vi.fn(),
  useFilesGlobalMock: vi.fn(),
}));

vi.mock("../queries/useSessions", () => ({ useSessions: () => useSessionsMock() }));
vi.mock("../queries/useFiles", () => ({ useFilesGlobal: () => useFilesGlobalMock() }));
vi.mock("../lib/useSessionEvents", () => ({ useSessionEvents: () => {} }));

// Helper
const renderAppShell = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/app/chat"]}>
        <Routes>
          <Route path="/app/*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe("AppShell wizard trigger", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearWizardFlags();
    useWizardStore.setState({ open: false, engaged: false, manual: false, dismissed: false });
    useChatStore.setState({ isStreaming: false });
    useSessionsMock.mockReturnValue({ data: [], isLoading: false, isSuccess: true, isError: false });
    useFilesGlobalMock.mockReturnValue({ data: [], isLoading: false, isSuccess: true, isError: false });
  });

  afterEach(() => cleanup());

  const expectWizardVisible = async (visible: boolean) => {
    const expectation = visible ? "toBeTruthy" : "toBeNull";
    const query = visible ? "getByRole" : "queryByRole";
    await waitFor(() => expect(screen[query]("dialog", { name: /first-run wizard/i }))[expectation]());
  };

  it("auto-opens for fresh user", async () => {
    renderAppShell();
    await expectWizardVisible(true);
  });

  it("hides with 1+ sessions", async () => {
    useSessionsMock.mockReturnValue({ data: [{ id: "ses-1", title: "Test" }], isLoading: false, isSuccess: true });
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("hides with 1+ files", async () => {
    useFilesGlobalMock.mockReturnValue({ data: [{ id: 1, filename: "test.csv", format: "csv", size_bytes: 1024 }], isLoading: false, isSuccess: true });
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("hides while sessions loading", () => {
    useSessionsMock.mockReturnValue({ data: undefined, isLoading: true, isSuccess: false });
    renderAppShell();
    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("hides while files loading", () => {
    useFilesGlobalMock.mockReturnValue({ data: undefined, isLoading: true, isSuccess: false });
    renderAppShell();
    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("hides while streaming", async () => {
    useChatStore.setState({ isStreaming: true });
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("auto-closes when sessions appear un-engaged", async () => {
    renderAppShell();
    await expectWizardVisible(true);
    cleanup();
    
    useSessionsMock.mockReturnValue({ data: [{ id: "ses-1", title: "New" }], isLoading: false, isSuccess: true });
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("stays open when engaged despite sessions", async () => {
    renderAppShell();
    await expectWizardVisible(true);
    
    useWizardStore.setState({ engaged: true });
    useSessionsMock.mockReturnValue({ data: [{ id: "ses-1", title: "New" }], isLoading: false, isSuccess: true });
    
    cleanup();
    renderAppShell();
    await expectWizardVisible(true);
  });

  it("stays open when manual despite sessions", async () => {
    useWizardStore.setState({ open: true, manual: true });
    useSessionsMock.mockReturnValue({ data: [{ id: "ses-1", title: "Existing" }], isLoading: false, isSuccess: true });
    
    renderAppShell();
    await expectWizardVisible(true);
  });

  it("persists skipped state", async () => {
    renderAppShell();
    await expectWizardVisible(true);
    
    fireEvent.click(screen.getByText("Skip"));
    await expectWizardVisible(false);
    
    cleanup();
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("reopens manually after skip (spec: reopen regardless of persisted flags)", async () => {
    renderAppShell();
    await expectWizardVisible(true);

    fireEvent.click(screen.getByText("Skip"));
    await expectWizardVisible(false);

    // The ChatView empty-state reopen control calls openWizard(true)
    useWizardStore.getState().openWizard(true);
    await expectWizardVisible(true);
  });

  it("hides when previously completed", async () => {
    useWizardStore.setState({ dismissed: true });
    renderAppShell();
    await expectWizardVisible(false);
  });
});