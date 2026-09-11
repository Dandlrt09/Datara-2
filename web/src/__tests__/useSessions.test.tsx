import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, renderHook, waitFor, act, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSessions, useCreateSession, useDeleteSession } from "../queries/useSessions";
import { useSseStore } from "../stores/useSseStore";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import AppShell from "../routes/AppShell";

// Mock the api module
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock the SSE hook so we can capture the onEvent callback AppShell passes in
vi.mock("../lib/useSessionEvents", () => ({
  useSessionEvents: (opts: { onEvent?: (e: unknown) => void } = {}) => {
    (globalThis as { __capturedOnEvent?: (e: unknown) => void }).__capturedOnEvent =
      opts.onEvent;
    return { state: "open" };
  },
}));

// Mock sessions and files queries so AppShell doesn't make real API calls
// Only mock useSessions and useFilesGlobal, not useCreateSession/useDeleteSession
// so the hook tests can test the real implementations
vi.mock("../queries/useSessions", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...original,
    useSessions: () => ({
      data: [],
      isLoading: false,
      isSuccess: true,
      isError: false,
    }),
  };
});

vi.mock("../queries/useFiles", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...original,
    useFilesGlobal: () => ({
      data: [],
      isLoading: false,
      isSuccess: true,
      isError: false,
    }),
  };
});

// Mock auth so AppShell mounts
vi.mock("../queries/useAuth", () => ({
  useMe: () => ({
    data: { id: 1, email: "u@x" },
    isLoading: false,
    error: null,
  }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// Mock chat store
vi.mock("../stores/useChatStore", () => ({
  useChatStore: () => ({
    isStreaming: false,
  }),
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

// Mock SSE store
vi.mock("../stores/useSseStore", () => ({
  useSseStore: () => ({
    setSseState: vi.fn(),
  }),
}));

// Mock react-router so AppShell doesn't require a real router context
vi.mock("react-router-dom", () => ({
  Routes: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Route: () => null,
  useNavigate: () => vi.fn(),
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

// Regression: lock the cross-slice integration between the SSE wire
// vocabulary (uppercase enum NAMES per spec R1) and the cache patch switch
// inside AppShell. If a future change reintroduces the dotted lowercase
// vocabulary on the frontend, every event will fall through to `default`
// and the streaming indicator + title cache updates silently fail.
describe("AppShell SSE event → cache patch wiring (regression)", () => {
  let qc: QueryClient;

  beforeEach(() => {
    cleanup();
    qc = createTestQueryClient();
    (globalThis as { __capturedOnEvent?: (e: unknown) => void }).__capturedOnEvent = undefined;
    render(<AppShell />, { wrapper: ({ children }) => <Wrapper qc={qc}>{children}</Wrapper> });
  });

  function captured(): (e: unknown) => void {
    const fn = (globalThis as { __capturedOnEvent?: (e: unknown) => void }).__capturedOnEvent;
    expect(fn).toBeDefined();
    return fn as (e: unknown) => void;
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
});