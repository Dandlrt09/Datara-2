import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, cleanup, act } from "@testing-library/react";
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

// Helper — accepts an optional pre-built QueryClient so a test can register
// mutations (e.g. an in-flight ["createSession"]) BEFORE AppShell mounts, which
// is the literal spec precondition "trigger conditions appear met while a
// session creation is in flight".
const renderAppShell = (prebuiltClient?: QueryClient) => {
  const queryClient = prebuiltClient ?? new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/app/chat"]}>
        <Routes>
          <Route path="/app/*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  return { ...result, queryClient };
};

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

/**
 * Register a still-pending mutation under the shared ["createSession"] key so
 * AppShell's `useIsMutating` can observe it, mirroring a view (e.g. FilesView)
 * that started the session creation from its own hook instance.
 */
function startPendingCreateSession(queryClient: QueryClient) {
  let settle: () => void = () => {};
  const mutation = queryClient.getMutationCache().build(queryClient, {
    mutationKey: ["createSession"],
    mutationFn: () =>
      new Promise<void>((resolve) => {
        settle = resolve;
      }),
  });
  void mutation.execute(undefined);
  return { settle };
}

describe("AppShell wizard trigger", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearWizardFlags();
    useWizardStore.setState({ open: false, engaged: false, manual: false, dismissed: false });
    useChatStore.setState({ isStreaming: false });
    useSessionsMock.mockReturnValue({ data: [], isLoading: false, isSuccess: true, isError: false });
    useFilesGlobalMock.mockReturnValue({
      data: [],
      isLoading: false,
      isSuccess: true,
      isError: false,
      hasMore: false,
      loadMore: vi.fn(),
      isLoadingMore: false,
    });
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
    useFilesGlobalMock.mockReturnValue({ data: [{ id: 1, filename: "test.csv", format: "csv", size_bytes: 1024 }], isLoading: false, isSuccess: true, hasMore: false, loadMore: vi.fn(), isLoadingMore: false });
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("hides while sessions loading", () => {
    useSessionsMock.mockReturnValue({ data: undefined, isLoading: true, isSuccess: false });
    renderAppShell();
    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("hides while files loading", () => {
    useFilesGlobalMock.mockReturnValue({ data: undefined, isLoading: true, isSuccess: false, hasMore: false, loadMore: vi.fn(), isLoadingMore: false });
    renderAppShell();
    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("hides while streaming", async () => {
    useChatStore.setState({ isStreaming: true });
    renderAppShell();
    await expectWizardVisible(false);
  });

  it("does not auto-open while a session creation is in flight, and stays closed once the session lands", async () => {
    // Register the pending mutation on the shared cache BEFORE AppShell mounts,
    // so the very first render already sees an in-flight session creation. This
    // is the literal spec precondition: trigger conditions appear met (resolved
    // empty caches) WHILE a session creation is in flight.
    const queryClient = makeQueryClient();
    const { settle } = startPendingCreateSession(queryClient);
    await waitFor(() =>
      expect(queryClient.isMutating({ mutationKey: ["createSession"] })).toBe(1),
    );

    renderAppShell(queryClient);

    // The mutation is globally visible under ["createSession"] even though it was
    // not started by AppShell's own hook instance (react-query v5 state is per-instance).
    expect(queryClient.isMutating({ mutationKey: ["createSession"] })).toBe(1);
    // Resolved-empty caches would normally trigger the auto-open on mount; the
    // pending session creation must suppress it for the whole flight window.
    await expectWizardVisible(false);

    // Simulate the created session landing in the cache, then settle the mutation.
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-new", title: "New session" }],
      isLoading: false,
      isSuccess: true,
      isError: false,
    });
    await act(async () => {
      settle();
      await Promise.resolve();
    });

    // The session is present, so the wizard stays closed after the settle.
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