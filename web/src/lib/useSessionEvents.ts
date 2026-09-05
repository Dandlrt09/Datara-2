import { useCallback, useEffect, useRef, useState } from "react";
import { parseSSEFrames } from "./sse";
import { useSseStore, type SseState } from "../stores/useSseStore";

export interface SessionEvent {
  type: string;
  session_id: string;
  timestamp: number;
  payload: Record<string, unknown>;
}

export interface UseSessionEventsOptions {
  onEvent?: (event: SessionEvent) => void;
  onReconnected?: () => void;
}

const MAX_RETRIES = 10;

function backoffDelay(attempt: number): number {
  const base = Math.min(30_000, 500 * 2 ** attempt);
  return base * (0.5 + Math.random() * 0.5);
}

/**
 * Hook that connects to `/api/sessions/events` via fetch-stream,
 * parses SSE frames using the shared `parseSSEFrames` helper, and
 * provides jittered capped-exponential backoff reconnection.
 *
 * - 4xx (except 429) → fatal (no retry)
 * - 5xx or 429 → retry with jittered backoff
 * - Backoff exhaustion → fatal
 * - Unmount → abort + cleanup
 */
export function useSessionEvents(opts?: UseSessionEventsOptions) {
  const setSseState = useSseStore((s) => s.setSseState);
  const [state, setState] = useState<SseState>("connecting");
  const attemptRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const onEventRef = useRef(opts?.onEvent);
  const onReconnectedRef = useRef(opts?.onReconnected);
  onEventRef.current = opts?.onEvent;
  onReconnectedRef.current = opts?.onReconnected;

  const connect = useCallback(async () => {
    if (!mountedRef.current) return;

    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;
    const signal = abort.signal;

    const attempt = attemptRef.current;

    // Apply backoff delay before connecting, except for the initial connection
    if (attempt > 0) {
      const delay = backoffDelay(attempt);
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, delay);
        const onAbort = () => {
          clearTimeout(timer);
          resolve();
        };
        signal.addEventListener("abort", onAbort, { once: true });
      });
      if (signal.aborted || !mountedRef.current) return;
    }

    // Set state to connecting only on first attempt
    if (attempt === 0) {
      updateState("connecting");
    } else {
      updateState("reconnecting");
    }

    let response: Response;
    try {
      response = await fetch("/api/sessions/events", {
        credentials: "include",
        signal,
      });
    } catch (err) {
      if (!mountedRef.current || signal.aborted) return;
      // Network error — treat as transient, retry
      attemptRef.current++;
      retryOrFatal();
      return;
    }

    if (signal.aborted || !mountedRef.current) return;

    // Handle HTTP status codes
    if (response.status >= 400) {
      if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        // 4xx except 429 → fatal
        updateState("fatal");
        return;
      }
      // 429 or 5xx → retry with backoff
      attemptRef.current++;
      retryOrFatal();
      return;
    }

    // Successful connection
    const wasReconnecting = attemptRef.current > 0;
    attemptRef.current = 0; // Reset on first successful reconnect
    updateState("open");

    if (wasReconnecting) {
      onReconnectedRef.current?.();
    }

    // Stream the response body
    const reader = response.body?.getReader();
    if (!reader) {
      attemptRef.current++;
      retryOrFatal();
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (signal.aborted || !mountedRef.current) {
          reader.cancel();
          return;
        }
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          if (!frame.trim()) continue;
          const parsed = parseSSEFrames(frame);
          const data = parsed.data as Record<string, unknown> | null;
          if (data && typeof data === "object") {
            const event: SessionEvent = {
              type: parsed.event,
              session_id: (data.session_id as string) ?? "",
              timestamp: (data.timestamp as number) ?? Date.now() / 1000,
              payload: (data.payload as Record<string, unknown>) ?? {},
            };
            onEventRef.current?.(event);
          }
        }
      }
    } catch (err) {
      if (signal.aborted || !mountedRef.current) return;
      // Stream error — retry
      attemptRef.current++;
      retryOrFatal();
      return;
    }

    // Stream ended cleanly — retry
    attemptRef.current++;
    retryOrFatal();

    function updateState(s: SseState) {
      if (!mountedRef.current) return;
      setState(s);
      setSseState(s);
    }

    function retryOrFatal() {
      if (attemptRef.current > MAX_RETRIES) {
        updateState("fatal");
        return;
      }
      // Schedule next reconnect attempt via microtask
      queueMicrotask(() => {
        if (mountedRef.current) connect();
      });
    }
  }, [setSseState]);

  useEffect(() => {
    mountedRef.current = true;
    // Reset attempt counter on mount
    attemptRef.current = 0;
    const timer = setTimeout(() => connect(), 0);

    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      clearTimeout(timer);
    };
  }, [connect]);

  return { state };
}