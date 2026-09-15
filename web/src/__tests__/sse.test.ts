import { describe, it, expect, vi } from "vitest";
import { streamChat } from "../lib/sse";

function mockFetchStream(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  let index = 0;
  globalThis.fetch = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          function push() {
            if (index >= chunks.length) {
              controller.close();
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
      }
    );
}

describe("streamChat SSE parser", () => {
  it("parses multi-event chunk", async () => {
    mockFetchStream([
      "event: status\ndata: {\"stage\":\"llm\",\"state\":\"done\"}\n\nevent: token\ndata: \"Hello\"\n\nevent: done\ndata: {\"message_id\":42}\n\n",
    ]);

    const handlers = {
      onStatus: vi.fn(),
      onToken: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    };

    await streamChat("ses-1", "hello", handlers);

    expect(handlers.onStatus).toHaveBeenCalledWith("llm", "done");
    expect(handlers.onToken).toHaveBeenCalledWith("Hello");
    expect(handlers.onDone).toHaveBeenCalledWith(42);
    expect(handlers.onError).not.toHaveBeenCalled();
  });

  it("handles frames split across chunks", async () => {
    mockFetchStream([
      "event: status\ndata: {\"stage\":\"llm\",\"state",
      "\":\"done\"}\n\nevent: token\ndata: \"W",
      "orld\"\n\n",
    ]);

    const handlers = {
      onStatus: vi.fn(),
      onToken: vi.fn(),
      onError: vi.fn(),
    };

    await streamChat("ses-1", "hello", handlers);

    expect(handlers.onStatus).toHaveBeenCalledWith("llm", "done");
    expect(handlers.onToken).toHaveBeenCalledWith("World");
    expect(handlers.onError).not.toHaveBeenCalled();
  });

  it("parses error event", async () => {
    const payload = '{"type":"blocked_import","message":"os is blocked"}';
    mockFetchStream([`event: error\ndata: ${payload}\n\n`]);

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith("blocked_import", "os is blocked");
  });

  it("handles HTTP error response", async () => {
    mockFetchStream([], 401);

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith("connection_error", "HTTP 401");
  });

  it("aborts silently during the fetch window (before headers arrive)", async () => {
    // Regression: the AbortError swallow used to wrap only the reader loop;
    // a Detener click while fetch was still pending (server pre-stream DB
    // writes + RTT) rejected streamChat and surfaced a spurious error
    // banner. Abort must be silent across the ENTIRE streamChat lifecycle.
    const controller = new AbortController();
    globalThis.fetch = (_url, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });

    const handlers = {
      onError: vi.fn(),
    };

    const pending = streamChat("ses-1", "hello", handlers, controller.signal);
    controller.abort();
    await expect(pending).resolves.toBeUndefined();
    expect(handlers.onError).not.toHaveBeenCalled();
  });
});