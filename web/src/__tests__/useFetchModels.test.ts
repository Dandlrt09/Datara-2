import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useFetchModels, type ModelsResponse } from "../routes/setup/useFetchModels";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: { post: vi.fn() },
}));

const postMock = vi.mocked(api.post);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return createElement(QueryClientProvider, { client }, children);
}

describe("useFetchModels", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("resolves models when the probe succeeds", async () => {
    postMock.mockResolvedValue({ models: [{ id: "gpt-4o", name: "gpt-4o" }], error: null });
    const { result } = renderHook(() => useFetchModels(), { wrapper });

    const response = await result.current.fetchModels();
    expect(response).toEqual({ models: [{ id: "gpt-4o", name: "gpt-4o" }], error: null });
    expect(postMock.mock.calls[0]?.[0]).toBe("/api/settings/models");
  });

  it("resolves a timeout error when the probe hangs past 15 seconds (R3-002)", async () => {
    // Render under real timers (react-query's scheduler stalls under fakes),
    // then fake only the clock that drives the hook's timeout.
    const { result } = renderHook(() => useFetchModels(), { wrapper });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    // A hung transport: the POST never settles.
    postMock.mockReturnValue(new Promise<ModelsResponse>(() => {}));
    const pending = result.current.fetchModels();
    // Async tick: it flushes the microtask queue that defers react-query's
    // mutationFn (which registers the hook's timer) before advancing.
    await vi.advanceTimersByTimeAsync(15_000);

    await expect(pending).resolves.toEqual({
      models: [],
      error: { code: "timeout", message: "Request timed out" },
    });
  });
});
