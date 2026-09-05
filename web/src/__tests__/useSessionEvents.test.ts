import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useSessionEvents } from "../lib/useSessionEvents";

/** Create a readable stream that stays open (never closes). */
function mockOpenStream(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  let index = 0;
  globalThis.fetch = vi.fn().mockImplementation(async () => {
    return new Response(
      new ReadableStream({
        start(controller) {
          function push() {
            if (index >= chunks.length) {
              // Keep stream open — never close
              return;
            }
            controller.enqueue(encoder.encode(chunks[index]));
            index++;
            push();
          }
          push();
        },
      }),
      {
        status,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  });
}

/** Create a mock fetch that returns a given HTTP status (no body stream). */
function mockHttpStatus(status: number) {
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response(null, { status, headers: {} }),
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("useSessionEvents", () => {
  it("connects to SSE and reaches open state on 200", async () => {
    mockOpenStream(["event: CREATED\nid: s1:100\ndata: {}\n\n"]);
    const onEvent = vi.fn();

    const { result } = renderHook(() => useSessionEvents({ onEvent }));

    // Advance past the setTimeout(0) that calls connect()
    await act(() => vi.advanceTimersByTimeAsync(10));
    await vi.waitFor(() => expect(result.current.state).toBe("open"));
  });

  it("parses an SSE event and calls onEvent callback", async () => {
    const frame =
      'event: STREAMING_STARTED\nid: s1:100\ndata: {"session_id":"s1","timestamp":100,"payload":{"is_streaming":true}}\n\n';
    mockOpenStream([frame]);
    const onEvent = vi.fn();

    renderHook(() => useSessionEvents({ onEvent }));

    await act(() => vi.advanceTimersByTimeAsync(10));
    await vi.waitFor(() => {
      expect(onEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "STREAMING_STARTED",
          session_id: "s1",
          timestamp: 100,
          payload: { is_streaming: true },
        }),
      );
    });
  });

  it("fatal on 401 — does not retry", async () => {
    mockHttpStatus(401);

    const { result } = renderHook(() => useSessionEvents());

    await act(() => vi.advanceTimersByTimeAsync(10));
    await vi.waitFor(() => expect(result.current.state).toBe("fatal"));

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it("fatal on 403 — does not retry", async () => {
    mockHttpStatus(403);

    const { result } = renderHook(() => useSessionEvents());

    await act(() => vi.advanceTimersByTimeAsync(10));
    await vi.waitFor(() => expect(result.current.state).toBe("fatal"));

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it("retries on 500 with backoff", async () => {
    let callCount = 0;
    const fetchFn = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount <= 3) {
        return new Response(null, { status: 503, headers: {} });
      }
      // After 3 failures, succeed with an open stream
      return new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode(
                'event: CREATED\nid: s1:200\ndata: {"session_id":"s1","timestamp":200,"payload":{}}\n\n',
              ),
            );
            // Stay open
          },
        }),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      );
    });
    globalThis.fetch = fetchFn;

    renderHook(() => useSessionEvents());

    // Let the initial connect run (attempt=0, no delay)
    await act(() => vi.advanceTimersByTimeAsync(50));
    // After first 503, attempt=1, backoff ~500-1500ms
    await act(() => vi.advanceTimersByTimeAsync(2000));
    // After second 503, attempt=2, backoff ~1000-3000ms
    await act(() => vi.advanceTimersByTimeAsync(4000));
    // After third 503, attempt=3, backoff ~2000-6000ms — should succeed
    await act(() => vi.advanceTimersByTimeAsync(8000));

    // Should have called fetch 4 times (3 fails + 1 success)
    expect(fetchFn).toHaveBeenCalledTimes(4);
  });

  it("retries on 429 with backoff", async () => {
    let callCount = 0;
    const fetchFn = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount === 1) {
        return new Response(null, { status: 429, headers: {} });
      }
      return new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode(
                'event: CREATED\nid: s1:200\ndata: {"session_id":"s1","timestamp":200,"payload":{}}\n\n',
              ),
            );
          },
        }),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      );
    });
    globalThis.fetch = fetchFn;

    renderHook(() => useSessionEvents());

    // Let initial connect run
    await act(() => vi.advanceTimersByTimeAsync(50));
    // After 429, attempt=1, backoff ~500-1500ms
    await act(() => vi.advanceTimersByTimeAsync(2000));

    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it("aborts on unmount", async () => {
    // Use real timers for this test to ensure synchronous abort behavior
    vi.useRealTimers();

    const abortSpy = vi.fn();
    const fetchFn = vi.fn().mockImplementation(
      (_url: string, opts: { signal: AbortSignal }) => {
        const { signal } = opts;
        signal.addEventListener("abort", abortSpy, { once: true });
        // Return a never-resolving promise so connect stays in-flight
        return new Promise<Response>(() => {});
      },
    );
    globalThis.fetch = fetchFn;

    const { unmount } = renderHook(() => useSessionEvents());

    // Yield to event loop so setTimeout(0) fires and connect() starts
    await new Promise<void>((resolve) => setTimeout(resolve, 10));

    // fetchFn should have been called — connect is now awaiting fetch
    expect(fetchFn).toHaveBeenCalled();

    // Unmount triggers abort
    unmount();

    // AbortController.abort() fires synchronously
    expect(abortSpy).toHaveBeenCalled();
  });
});