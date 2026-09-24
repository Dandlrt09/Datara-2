import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, renderHook, waitFor, act, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSessions, useCreateSession, useDeleteSession, useRenameSession } from "../queries/useSessions";
import { useSseStore } from "../stores/useSseStore";
import { useChatStore } from "../stores/useChatStore";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import AppShell from "../routes/AppShell";

// Mock the api module
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock the SSE hook so we can capture the onEvent callback AppShell passes in
vi.mock("../lib/useSessionEvents", () => ({
  useSessionEvents: (
    opts: {
      onEvent?: (e: unknown) => void;
      onReconnected?: () => void;
    } = {},
  ) => {
    (globalThis as { __capturedOnEvent?: (e: unknown) => void }).__capturedOnEvent =
      opts.onEvent;
    (globalThis as { __capturedOnReconnected?: () => void }).__capturedOnReconnected =
      opts.onReconnected;
    return { state: "open" };
  },
}));



// Mock auth so AppShell mounts
vi.mock("../queries/useAuth", () => ({
  useMe: () => ({
    data: { id: 1, email: "u@x" },
    isLoading: false,
    error: null,
  }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// Mock wizard store  
vi.mock("../stores/useWizardStore", () => ({
  useWizardStore: () => ({
    open: false,
    engaged: false,
    manual: false,
    dismissed: false,
    openWizard: vi.fn(),
    closeWizard: vi.fn(),
  }),
}));



// Stable navigate spy so tests can assert on cross-session navigation.
const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }));

// Mock react-router so AppShell doesn't require a real router context
vi.mock("react-router-dom", () => ({
  Routes: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Route: () => null,
  useNavigate: () => navigateMock,
  Link: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock the lazy-loaded views so AppShell can render without pulling in
// real ChatView/FilesView/SettingsView/ArchiveList
vi.mock("../routes/ChatView", () => ({ default: () => null }));
vi.mock("../routes/FilesView", () => ({ default: () => null }));
vi.mock("../routes/SettingsView", () => ({ default: () => null }));
vi.mock("../routes/ArchiveList", () => ({ default: () => null }));

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function Wrapper({ children, qc }: { children: ReactNode; qc: QueryClient }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_SESSIONS = [
  { id: "s1", title: "Chat 1", created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
  { id: "s2", title: "Chat 2", created_at: "2024-01-02T00:00:00Z", updated_at: "2024-01-02T00:00:00Z" },
];

type CachedSession = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_streaming?: boolean;
};

describe("useSessions", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = createTestQueryClient();
    vi.clearAllMocks();
    (api.get as Mock).mockResolvedValue(MOCK_SESSIONS);
  });

  it("fetches sessions on mount", async () => {
    act(() => {
      useSseStore.getState().setSseState("fatal");
    });

    const { result } = renderHook(() => useSessions(), {
      wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper>,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 10_000 });
    expect(result.current.data).toEqual(MOCK_SESSIONS);
  });

  it("does NOT poll when SSE is connected — single fetch", async () => {
    act(() => {
      useSseStore.getState().setSseState("open");
    });

    const { result } = renderHook(() => useSessions(), {
      wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper>,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 10_000 });

    // Only one fetch should have occurred (no polling since SSE is connected)
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it("polls when SSE is disconnected", async () => {
    vi.useFakeTimers();
    (api.get as Mock).mockResolvedValue(MOCK_SESSIONS);

    act(() => {
      useSseStore.getState().setSseState("fatal");
    });

    const { result } = renderHook(() => useSessions(), {
      wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper>,
    });

    // Initial fetch should resolve
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 10_000 });
    expect(api.get).toHaveBeenCalledTimes(1);

    // Advance fake timers beyond the 10s refetchInterval
    await act(() => { vi.advanceTimersByTime(12_000); });
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(2), { timeout: 10_000 });

    vi.useRealTimers();
  });
});

describe("useCreateSession", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = createTestQueryClient();
    vi.clearAllMocks();
    (api.post as Mock).mockResolvedValue(MOCK_SESSIONS[0]);
  });

  it("invalidates sessions on success", async () => {
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useCreateSession(), {
      wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper>,
    });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sessions"] });
  });
});

describe("useDeleteSession", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = createTestQueryClient();
    vi.clearAllMocks();
    (api.delete as Mock).mockResolvedValue(undefined);
  });

  it("invalidates sessions on success", async () => {
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useDeleteSession(), {
      wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper>,
    });

    await act(async () => {
      await result.current.mutateAsync("s1");
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sessions"] });
  });
});

describe("useRenameSession", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = createTestQueryClient();
    vi.clearAllMocks();
    (api.patch as Mock).mockResolvedValue(MOCK_SESSIONS[0]);
  });

  it("PATCHes the session title and invalidates sessions on success", async () => {
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useRenameSession(), {
      wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper>,
    });

    await act(async () => {
      await result.current.mutateAsync({ id: "s1", title: "Nuevo título" });
    });

    expect(api.patch).toHaveBeenCalledWith("/api/sessions/s1", {
      title: "Nuevo título",
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sessions"] });
  });
});

// Regression: lock the cross-slice integration between the SSE wire
// vocabulary (uppercase enum NAMES per spec R1) and the cache patch switch
// inside AppShell. If a future change reintroduces the dotted lowercase
// vocabulary on the frontend, every event will fall through to `default`
// and the streaming indicator + title cache updates silently fail.
describe("AppShell SSE event → cache patch wiring (regression)", () => {
  let qc: QueryClient;

  beforeEach(() => {
    // AppShell mounts the REAL useSessions/useFilesGlobal hooks: a module
    // mock here would break the hook tests above, and vi.doMock does not
    // affect already-evaluated static imports. This suite's premise is a
    // failed initial fetch (backend restarting), so make api.get reject —
    // otherwise the leftover mockResolvedValue from the hook tests above
    // populates the cache and the invalidate branch never fires.
    (api.get as Mock).mockRejectedValue(new Error("backend restarting"));
    cleanup();
    qc = createTestQueryClient();
    navigateMock.mockClear();
    useChatStore.setState({ historyReset: null, activeSessionId: null });
    (globalThis as { __capturedOnEvent?: (e: unknown) => void }).__capturedOnEvent = undefined;
    (globalThis as { __capturedOnReconnected?: () => void }).__capturedOnReconnected = undefined;
    render(<AppShell />, { wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper> });
  });

  function captured(): (e: unknown) => void {
    const fn = (globalThis as { __capturedOnEvent?: (e: unknown) => void }).__capturedOnEvent;
    expect(fn).toBeDefined();
    return fn as (e: unknown) => void;
  }

  function capturedReconnected(): () => void {
    const fn = (globalThis as { __capturedOnReconnected?: () => void })
      .__capturedOnReconnected;
    expect(fn).toBeDefined();
    return fn as () => void;
  }

  it("TITLED (wire vocabulary: uppercase enum name) patches cache title", () => {
    qc.setQueryData<{ id: string; title: string }[]>(["sessions"], [
      { id: "s1", title: "New chat" },
    ]);
    captured()({
      type: "TITLED",
      session_id: "s1",
      timestamp: 100,
      payload: { title: "Auto title" },
    });
    const cached = qc.getQueryData<{ id: string; title: string }[]>([
      "sessions",
    ]);
    expect(cached?.[0]?.title).toBe("Auto title");
  });

  it("STREAMING_STARTED (wire vocabulary) sets is_streaming=true", () => {
    qc.setQueryData<{ id: string; title: string; is_streaming?: boolean }[]>(
      ["sessions"],
      [{ id: "s1", title: "t" }],
    );
    captured()({
      type: "STREAMING_STARTED",
      session_id: "s1",
      timestamp: 100,
      payload: { is_streaming: true },
    });
    const cached = qc.getQueryData<
      { id: string; title: string; is_streaming?: boolean }[]
    >(["sessions"]);
    expect(cached?.[0]?.is_streaming).toBe(true);
  });

  it("STREAMING_ENDED (wire vocabulary) clears is_streaming", () => {
    qc.setQueryData<{ id: string; title: string; is_streaming?: boolean }[]>(
      ["sessions"],
      [{ id: "s1", title: "t", is_streaming: true }],
    );
    captured()({
      type: "STREAMING_ENDED",
      session_id: "s1",
      timestamp: 100,
      payload: { is_streaming: false },
    });
    const cached = qc.getQueryData<
      { id: string; title: string; is_streaming?: boolean }[]
    >(["sessions"]);
    expect(cached?.[0]?.is_streaming).toBe(false);
  });

  it("CREATED inserts a new session and puts it first (newest updated_at)", () => {
    qc.setQueryData<CachedSession[]>(["sessions"], [
      {
        id: "old",
        title: "Old",
        created_at: "2024-01-01 00:00:00",
        updated_at: "2024-01-01 00:00:00",
      },
    ]);
    captured()({
      type: "CREATED",
      session_id: "new",
      timestamp: 100,
      payload: {
        session: {
          id: "new",
          title: "New",
          created_at: "2024-02-01 00:00:00",
          updated_at: "2024-02-01 00:00:00",
          is_streaming: false,
        },
      },
    });
    const cached = qc.getQueryData<CachedSession[]>(["sessions"]);
    expect(cached?.map((s) => s.id)).toEqual(["new", "old"]);
    expect(cached?.[0]).toEqual({
      id: "new",
      title: "New",
      created_at: "2024-02-01 00:00:00",
      updated_at: "2024-02-01 00:00:00",
      is_streaming: false,
    });
  });

  it("CREATED with a malformed payload leaves the cache unchanged", () => {
    const before: CachedSession[] = [
      {
        id: "old",
        title: "Old",
        created_at: "2024-01-01 00:00:00",
        updated_at: "2024-01-01 00:00:00",
      },
    ];
    qc.setQueryData<CachedSession[]>(["sessions"], before);
    captured()({
      type: "CREATED",
      session_id: "new",
      timestamp: 100,
      payload: {},
    });
    expect(qc.getQueryData(["sessions"])).toEqual(before);
  });

  it("UPDATED touches only updated_at, re-sorts, and preserves is_streaming", () => {
    qc.setQueryData<CachedSession[]>(["sessions"], [
      {
        id: "a",
        title: "A",
        created_at: "2024-01-01 00:00:00",
        updated_at: "2024-01-01 00:00:00",
        is_streaming: true,
      },
      {
        id: "b",
        title: "B",
        created_at: "2024-02-01 00:00:00",
        updated_at: "2024-02-01 00:00:00",
      },
    ]);
    captured()({
      type: "UPDATED",
      session_id: "a",
      timestamp: 100,
      payload: { updated_at: "2024-03-01 00:00:00" },
    });
    const cached = qc.getQueryData<CachedSession[]>(["sessions"]);
    expect(cached?.map((s) => s.id)).toEqual(["a", "b"]);
    expect(cached?.[0]).toEqual({
      id: "a",
      title: "A",
      created_at: "2024-01-01 00:00:00",
      updated_at: "2024-03-01 00:00:00",
      is_streaming: true,
    });
  });

  it("UPDATED with a missing payload timestamp leaves the cache unchanged", () => {
    const before: CachedSession[] = [
      {
        id: "a",
        title: "A",
        created_at: "2024-01-01 00:00:00",
        updated_at: "2024-01-01 00:00:00",
      },
    ];
    qc.setQueryData<CachedSession[]>(["sessions"], before);
    captured()({
      type: "UPDATED",
      session_id: "a",
      timestamp: 100,
      payload: {},
    });
    expect(qc.getQueryData(["sessions"])).toEqual(before);
  });

  it("DELETED removes the session without navigating when it is not active", () => {
    useChatStore.setState({ activeSessionId: "b", historyReset: null });
    qc.setQueryData<CachedSession[]>(["sessions"], [
      {
        id: "a",
        title: "A",
        created_at: "2024-01-01 00:00:00",
        updated_at: "2024-01-01 00:00:00",
      },
      {
        id: "b",
        title: "B",
        created_at: "2024-02-01 00:00:00",
        updated_at: "2024-02-01 00:00:00",
      },
    ]);
    captured()({
      type: "DELETED",
      session_id: "a",
      timestamp: 100,
      payload: {},
    });
    const cached = qc.getQueryData<CachedSession[]>(["sessions"]);
    expect(cached?.map((s) => s.id)).toEqual(["b"]);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("DELETED of the currently open session navigates to /app/chat", () => {
    useChatStore.setState({ activeSessionId: "a", historyReset: null });
    qc.setQueryData<CachedSession[]>(["sessions"], [
      {
        id: "a",
        title: "A",
        created_at: "2024-01-01 00:00:00",
        updated_at: "2024-01-01 00:00:00",
      },
    ]);
    captured()({
      type: "DELETED",
      session_id: "a",
      timestamp: 100,
      payload: {},
    });
    expect(qc.getQueryData<CachedSession[]>(["sessions"])).toEqual([]);
    expect(navigateMock).toHaveBeenCalledWith("/app/chat");
  });

  it("event with empty/failed cache invalidates instead of no-op", () => {
    // Regression: if the initial sessions fetch failed (e.g. backend restart
    // during page load), the cache is empty and patching would no-op — the
    // sidebar stayed dead until F5. The event must trigger a refetch instead.
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    // NO setQueryData — cache is empty (query never succeeded)
    captured()({
      type: "STREAMING_STARTED",
      session_id: "s1",
      timestamp: 100,
      payload: { is_streaming: true },
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    // ...and nothing was fabricated into the cache
    expect(qc.getQueryData(["sessions"])).toBeUndefined();
  });

  it("HISTORY_TRUNCATED bumps the chat store and leaves the sessions cache untouched", () => {
    // A truncating edit invalidates the chat pagination chain, not the
    // sidebar: the event must reach the chat store and `return old` so the
    // sessions cache is byte-for-byte unchanged.
    const sessionsBefore = [{ id: "s1", title: "t" }];
    qc.setQueryData<{ id: string; title: string }[]>(["sessions"], sessionsBefore);

    captured()({
      type: "HISTORY_TRUNCATED",
      session_id: "s1",
      timestamp: 100,
      payload: { from_message_id: 42 },
    });

    expect(useChatStore.getState().historyReset).toEqual({
      sessionId: "s1",
      nonce: 1,
    });
    expect(qc.getQueryData(["sessions"])).toEqual(sessionsBefore);
  });

  it("onReconnected bumps historyReset for the active session and invalidates sessions", () => {
    // Race 3: the event bus is best-effort, so a tab whose SSE stream was down
    // during a truncating edit never saw HISTORY_TRUNCATED. On reconnect the
    // active session must self-heal by firing the same reset signal.
    useChatStore.setState({ activeSessionId: "s1", historyReset: null });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    capturedReconnected()();

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(useChatStore.getState().historyReset).toEqual({
      sessionId: "s1",
      nonce: 1,
    });
  });

  it("onReconnected without an active session invalidates but does not bump", () => {
    useChatStore.setState({ activeSessionId: null, historyReset: null });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    capturedReconnected()();

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(useChatStore.getState().historyReset).toBeNull();
  });
});
