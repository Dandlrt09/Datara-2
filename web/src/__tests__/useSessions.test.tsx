import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSessions, useCreateSession, useDeleteSession } from "../queries/useSessions";
import { useSseStore } from "../stores/useSseStore";
import type { ReactNode } from "react";

// Mock the api module
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from "../lib/api";

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