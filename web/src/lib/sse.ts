/** SSE stream parser for chat endpoint.
 *
 * Uses fetch + ReadableStream chunk parser for SSE frames
 * (event/data pairs on \n\n). Native EventSource doesn't support
 * POST method or custom headers with credentials reliably.
 */

export type SSEEvent =
  | { event: "status"; data: { stage: string; state: string } }
  | { event: "token"; data: string }
  | { event: "artifact"; data: { figures: unknown[]; tables: unknown[]; texts?: unknown[] } }
  | { event: "done"; data: { message_id: number } }
  | {
      event: "error";
      data: { type: string; code?: string; message: string; traceback?: string };
    };

export interface SSEHandlers {
  onStatus?: (stage: string, state: string) => void;
  onToken?: (delta: string) => void;
  onArtifact?: (figures: unknown[], tables: unknown[], texts: unknown[]) => void;
  onDone?: (messageId: number) => void;
  /** code is the typed taxonomy code (e.g. "llm/timeout"); null when the
   * server did not send one (connection_error, legacy frames). */
  onError?: (type: string, code: string | null, message: string) => void;
}

export async function streamChat(
  sessionId: string,
  question: string,
  handlers: SSEHandlers,
  signal?: AbortSignal,
  retry = false
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/sessions/${sessionId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, retry }),
      credentials: "include",
      signal,
    });
  } catch (err) {
    // Abort before the response headers arrive (Detener clicked while the
    // server is still doing its pre-stream DB writes) must be silent,
    // exactly like an abort mid-stream. Genuine network failures still
    // throw so the caller can surface them.
    if ((err as Error).name === "AbortError") return;
    throw err;
  }

  if (!response.ok) {
    // The model-whitelist 422 carries a structured detail with the typed
    // code; anything else (unparseable body, other codes, other statuses)
    // keeps today's connection_error fallback.
    try {
      const body = (await response.json()) as {
        detail?: { code?: string; message?: string };
      };
      if (body.detail?.code === "model_not_allowed") {
        handlers.onError?.(
          "model",
          "model/not_allowed",
          body.detail.message ?? `HTTP ${response.status}`,
        );
        return;
      }
    } catch {
      // Non-JSON body → fall through to the generic handler.
    }
    handlers.onError?.("connection_error", null, `HTTP ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    handlers.onError?.("connection_error", null, "No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      // Keep the incomplete last chunk in the buffer
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        if (!frame.trim()) continue;
        parseFrame(frame, handlers);
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      handlers.onError?.("parse_error", null, String(err));
    }
  }
}

/** Parse a raw SSE frame string into its constituent fields.
 *
 * Returns the event type, event id, and parsed JSON data for each
 * complete frame. Intended for reuse by ``useSessionEvents`` which
 * consumes the session-level event stream (different wire format
 * from the chat stream).
 *
 * @param frame A complete SSE frame (up to but not including ``\n\n``).
 * @returns An object with ``event`` (string), ``id`` (string | null),
 *          and ``data`` (unknown — the JSON-parsed data field).
 */
export function parseSSEFrames(frame: string): { event: string; id: string | null; data: unknown } {
  let event = "message";
  let id: string | null = null;
  let dataRaw = "";

  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice(7);
    } else if (line.startsWith("id: ")) {
      id = line.slice(4);
    } else if (line.startsWith("data: ")) {
      dataRaw = line.slice(6);
    }
  }

  let data: unknown;
  try {
    data = JSON.parse(dataRaw);
  } catch {
    data = dataRaw;
  }

  return { event, id, data };
}

function parseFrame(frame: string, handlers: SSEHandlers): void {
  let event = "message";
  let dataRaw = "";

  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice(7);
    } else if (line.startsWith("data: ")) {
      dataRaw = line.slice(6);
    }
  }

  let data: unknown;
  try {
    data = JSON.parse(dataRaw);
  } catch {
    data = dataRaw;
  }

  switch (event) {
    case "status": {
      const d = data as { stage: string; state: string };
      handlers.onStatus?.(d.stage, d.state);
      break;
    }
    case "token":
      handlers.onToken?.(data as string);
      break;
    case "artifact": {
      const d = data as { figures?: unknown[]; tables?: unknown[]; texts?: unknown[] };
      // Degrade malformed payloads to empty lists instead of letting
      // undefined reach .map() and crash the whole view into the
      // ErrorBoundary.
      handlers.onArtifact?.(
        Array.isArray(d.figures) ? d.figures : [],
        Array.isArray(d.tables) ? d.tables : [],
        Array.isArray(d.texts) ? d.texts : [],
      );
      break;
    }
    case "done": {
      const d = data as { message_id: number };
      handlers.onDone?.(d.message_id);
      break;
    }
    case "error": {
      const d = data as {
        type: string;
        code?: string;
        message: string;
        traceback?: string;
      };
      // traceback is accepted on the wire but not rendered (kept for
      // future diagnostics); an absent code degrades to null.
      handlers.onError?.(d.type, d.code ?? null, d.message);
      break;
    }
  }
}