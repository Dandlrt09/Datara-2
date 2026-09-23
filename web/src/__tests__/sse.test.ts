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

  it("parses error event without code (degrades to null)", async () => {
    const payload = '{"type":"blocked_import","message":"os is blocked"}';
    mockFetchStream([`event: error\ndata: ${payload}\n\n`]);

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith(
      "blocked_import",
      null,
      "os is blocked",
    );
  });

  it("forwards the typed code on error frames that carry one", async () => {
    const payload =
      '{"type":"llm","code":"llm/timeout","message":"timed out","traceback":"..."}';
    mockFetchStream([`event: error\ndata: ${payload}\n\n`]);

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith(
      "llm",
      "llm/timeout",
      "timed out",
    );
  });

  it("handles HTTP error response without a JSON body", async () => {
    mockFetchStream([], 401);

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith(
      "connection_error",
      null,
      "HTTP 401",
    );
  });

  it("surfaces the model_not_allowed 422 detail with its typed code", async () => {
    // The whitelist 422 arrives BEFORE any SSE event; its structured body
    // must reach the banner as model/not_allowed, not connection_error.
    const encoder = new TextEncoder();
    globalThis.fetch = async () =>
      new Response(
        encoder.encode(
          JSON.stringify({
            detail: {
              code: "model_not_allowed",
              message: "El modelo 'x' no está permitido.",
            },
          }),
        ),
        { status: 422 },
      );

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith(
      "model",
      "model/not_allowed",
      "El modelo 'x' no está permitido.",
    );
  });

  it("falls back to connection_error on a non-JSON non-OK body", async () => {
    const encoder = new TextEncoder();
    globalThis.fetch = async () =>
      new Response(encoder.encode("<html>Gateway error</html>"), {
        status: 502,
      });

    const handlers = {
      onError: vi.fn(),
    };

    await streamChat("ses-1", "test", handlers);

    expect(handlers.onError).toHaveBeenCalledWith(
      "connection_error",
      null,
      "HTTP 502",
    );
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

  it("sends edit_message_id only when provided and keeps sending retry", async () => {
    const bodies: string[] = [];
    globalThis.fetch = async (_url, init) => {
      bodies.push(init?.body as string);
      return new Response(new ReadableStream({ start(c) { c.close(); } }), {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    };

    await streamChat("ses-1", "hola", {}, undefined, { retry: true });
    expect(JSON.parse(bodies[0])).toEqual({ question: "hola", retry: true });

    await streamChat("ses-1", "editada", {}, undefined, { editMessageId: 7 });
    expect(JSON.parse(bodies[1])).toEqual({
      question: "editada",
      retry: false,
      edit_message_id: 7,
    });

    await streamChat("ses-1", "normal", {}, undefined, {});
    expect(JSON.parse(bodies[2])).toEqual({ question: "normal", retry: false });
  });
});