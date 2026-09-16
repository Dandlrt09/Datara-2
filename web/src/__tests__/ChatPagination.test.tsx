import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { useChatStore } from "../stores/useChatStore";
import { renderWithProviders } from "./test-utils";
import ChatView from "../routes/ChatView";
import { MESSAGES_PAGE_SIZE } from "../queries/useMessages";

/**
 * Integration tests for chat-history pagination across the REAL wiring:
 * the real useMessages hook inside the real ChatView, with a stateful
 * fake backend modeled on the live contract (keyset windows, newest-first)
 * and turns completed through the SSE onDone flow — exactly like live.
 *
 * The unit suites mock one side each (hook tests mock `api.get`; ChatView
 * tests mock the whole hook), so nothing previously exercised the seam
 * "turn completes via SSE → hook refetch → hasMore/button" end to end.
 *
 * All expectations derive from MESSAGES_PAGE_SIZE so the suite stays valid
 * for any page-size value (e.g. the temporary live-test variant of 10 vs
 * the production 50).
 */

interface FakeMessage {
  id: number;
  role: string;
  content_text: string;
}

const START_ID = 208; // mirrors the live repro (ids 208-228)

/** Stateful fake backend: grows as turns complete, answers keyset windows
 * exactly like GET /api/sessions/{id}/messages (newest-first, before=id <).
 * Every message's content embeds its id (`mensaje-<id>`) so the rendered
 * order can be asserted from the DOM. */
function makeFakeServer(initialCount: number) {
  const messages: FakeMessage[] = [];
  let nextId = START_ID;
  for (let i = 0; i < initialCount; i++) {
    messages.push({
      id: nextId,
      role: i % 2 === 0 ? "user" : "assistant",
      content_text: `mensaje-${nextId}`,
    });
    nextId++;
  }
  return {
    messages,
    /** GET /api/sessions/ses-1/messages?limit=N&before=M */
    async get(url: string) {
      const limit = Number(url.match(/limit=(\d+)/)?.[1] ?? 50);
      const before = url.match(/before=(\d+)/);
      let pool = messages;
      if (before) pool = messages.filter((m) => m.id < Number(before[1]));
      return [...pool].sort((a, b) => b.id - a.id).slice(0, limit);
    },
    /** Server-side persist of a successful turn (question + answer), then
     * the terminal done frame — persist-then-emit, like the real endpoint. */
    async completeTurn(_question: string) {
      const questionId = nextId++;
      messages.push({
        id: questionId,
        role: "user",
        content_text: `mensaje-${questionId}`,
      });
      const answerId = nextId++;
      messages.push({
        id: answerId,
        role: "assistant",
        content_text: `mensaje-${answerId}`,
      });
    },
  };
}

const { apiGetMock, streamChatMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  streamChatMock: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  api: { get: apiGetMock, post: vi.fn(), delete: vi.fn() },
}));

vi.mock("../lib/sse", () => ({ streamChat: streamChatMock }));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => ({
    data: [{ id: "ses-1", title: "Chat 1" }],
    error: null,
    refetch: vi.fn(),
  }),
  useCreateSession: () => ({ mutateAsync: vi.fn() }),
  useDeleteSession: () => ({ mutate: vi.fn() }),
  useRenameSession: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../stores/useWizardStore", () => ({
  useWizardStore: () => ({ openWizard: vi.fn() }),
}));

vi.mock("../components/ChatMessage", () => ({
  default: ({ role, content }: { role: string; content: string }) => (
    <div data-testid={`msg-${role}`}>{content}</div>
  ),
}));

/** The app boots under StrictMode (main.tsx) — model it. */
function renderChat() {
  return renderWithProviders(
    <StrictMode>
      <ChatView />
    </StrictMode>,
    { route: "/app/chat/ses-1", path: "/app/chat/:sessionId" },
  );
}

function wireTurns(server: ReturnType<typeof makeFakeServer>) {
  streamChatMock.mockImplementation(
    async (_sid: string, q: string, handlers: { onDone?: () => void }) => {
      await server.completeTurn(q);
      handlers.onDone?.();
    },
  );
}

async function sendTurn(question: string) {
  fireEvent.change(screen.getByPlaceholderText(/Ask a question/), {
    target: { value: question },
  });
  fireEvent.click(screen.getByText("Send"));
  await waitFor(() => {
    expect(useChatStore.getState().isStreaming).toBe(false);
  });
}

function renderedIds(container: HTMLElement): number[] {
  return Array.from(
    container.querySelectorAll("[data-testid^='msg-']"),
  ).map((el) => Number((el.textContent ?? "").replace(/\D+/g, "")));
}

function expectContiguousIds(ids: number[], first: number, last: number) {
  const expected = Array.from(
    { length: last - first + 1 },
    (_, i) => first + i,
  );
  expect(ids).toEqual(expected);
}

describe("ChatPagination (real hook + real ChatView + live turn flow)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The chat store is a global Zustand singleton — reset streaming residue.
    useChatStore.setState({
      isStreaming: false,
      streamingText: "",
      pendingArtifacts: null,
    });
  });

  it("button appears exactly when the history reaches a full page while turns complete live", async () => {
    const server = makeFakeServer(0);
    apiGetMock.mockImplementation((url: string) => server.get(url));
    wireTurns(server);
    const view = renderChat();

    // 0 messages: nothing to page.
    await waitFor(() => {
      expect(apiGetMock).toHaveBeenCalled();
    });
    expect(screen.queryByText("Cargar mensajes anteriores")).toBeNull();

    // Turns below one full page: no affordance.
    while (server.messages.length < MESSAGES_PAGE_SIZE - 2) {
      const before = server.messages.length;
      await sendTurn("pregunta de crecimiento");
      await waitFor(() => {
        expect(renderedIds(view.container).length).toBe(before + 2);
      });
      expect(screen.queryByText("Cargar mensajes anteriores")).toBeNull();
    }

    // The turn that makes the history exactly one page → affordance appears.
    await sendTurn("pregunta que llena la página");
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(MESSAGES_PAGE_SIZE);
    });
    expect(await screen.findByText("Cargar mensajes anteriores")).toBeTruthy();

    // One more turn: the newest window slides up by 2 — the demoted window
    // must keep the slid-out messages (no gap), button stays visible.
    await sendTurn("pregunta que desliza la ventana");
    const total = MESSAGES_PAGE_SIZE + 2;
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(total);
    });
    expectContiguousIds(
      renderedIds(view.container),
      START_ID,
      START_ID + total - 1,
    );
    expect(screen.getByText("Cargar mensajes anteriores")).toBeTruthy();

    // Click: keyset cursor = oldest loaded id → only the 2 slid-out
    // messages remain older (2 < page size): history exhausted.
    fireEvent.click(screen.getByText("Cargar mensajes anteriores"));
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(total);
    });
    expectContiguousIds(
      renderedIds(view.container),
      START_ID,
      START_ID + total - 1,
    );
    expect(screen.queryByText("Cargar mensajes anteriores")).toBeNull();
  });

  it("fresh load of a completed longer-than-page session shows the affordance and pages back through the whole history", async () => {
    const total = 2 * MESSAGES_PAGE_SIZE + 1; // like the live 21 with page 10
    const server = makeFakeServer(total);
    apiGetMock.mockImplementation((url: string) => server.get(url));
    wireTurns(server);
    const view = renderChat();

    // Newest window (page-size of the total) → affordance on first render.
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(MESSAGES_PAGE_SIZE);
    });
    expect(await screen.findByText("Cargar mensajes anteriores")).toBeTruthy();

    // First click: a full older page.
    fireEvent.click(screen.getByText("Cargar mensajes anteriores"));
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(2 * MESSAGES_PAGE_SIZE);
    });
    expectContiguousIds(
      renderedIds(view.container),
      START_ID + 1,
      START_ID + total - 1,
    );
    expect(screen.getByText("Cargar mensajes anteriores")).toBeTruthy();

    // Second click: the single remaining message → short batch ends it.
    fireEvent.click(screen.getByText("Cargar mensajes anteriores"));
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(total);
    });
    expectContiguousIds(
      renderedIds(view.container),
      START_ID,
      START_ID + total - 1,
    );
    expect(screen.queryByText("Cargar mensajes anteriores")).toBeNull();
  });

  it("turns completing while older pages are loaded keep the loaded history gap-free and the next click heals the rest", async () => {
    const total = 2 * MESSAGES_PAGE_SIZE + 1;
    const server = makeFakeServer(total);
    apiGetMock.mockImplementation((url: string) => server.get(url));
    wireTurns(server);
    const view = renderChat();

    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(MESSAGES_PAGE_SIZE);
    });
    // Page back once: everything but the single oldest message.
    fireEvent.click(screen.getByText("Cargar mensajes anteriores"));
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(2 * MESSAGES_PAGE_SIZE);
    });
    expectContiguousIds(
      renderedIds(view.container),
      START_ID + 1,
      START_ID + total - 1,
    );

    // Live turn while paged: the newest window slides up by 2; the demotion
    // must keep the loaded history gap-free and duplicate-free.
    await sendTurn("pregunta en vivo");
    const loaded = 2 * MESSAGES_PAGE_SIZE + 2;
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(loaded);
    });
    // `loaded` counts RENDERED items: they span START_ID+1 .. START_ID+loaded
    // (the turn's two new messages included; 208 arrives on the next click).
    expectContiguousIds(
      renderedIds(view.container),
      START_ID + 1,
      START_ID + loaded,
    );
    expect(screen.getByText("Cargar mensajes anteriores")).toBeTruthy();

    // The next click fetches the remaining older message: the post-turn
    // history heals to the complete contiguous set.
    fireEvent.click(screen.getByText("Cargar mensajes anteriores"));
    await waitFor(() => {
      expect(renderedIds(view.container).length).toBe(loaded + 1);
    });
    expectContiguousIds(
      renderedIds(view.container),
      START_ID,
      START_ID + loaded,
    );
    expect(screen.queryByText("Cargar mensajes anteriores")).toBeNull();
  });
});
