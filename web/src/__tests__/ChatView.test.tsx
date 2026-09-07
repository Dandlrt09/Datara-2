import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, screen, waitFor } from "@testing-library/react";
import { useChatStore } from "../stores/useChatStore";
import { renderWithProviders } from "./test-utils";
import ChatView from "../routes/ChatView";

// ── Hook tests (existing) ────────────────────────────────────────────────────

describe("useChatStore", () => {
  it("accumulates streaming text", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.appendStreamingText("Hello");
    });
    expect(result.current.streamingText).toBe("Hello");

    act(() => {
      result.current.appendStreamingText(" World");
    });
    expect(result.current.streamingText).toBe("Hello World");
  });

  it("clears streaming text", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.appendStreamingText("Hello");
    });
    act(() => {
      result.current.clearStreamingText();
    });
    expect(result.current.streamingText).toBe("");
  });

  it("sets streaming state", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.setStreaming(true);
    });
    expect(result.current.isStreaming).toBe(true);
  });

  it("sets pending artifacts", () => {
    const { result } = renderHook(() => useChatStore());
    const artifacts = { figures: [{ name: "fig1" }], tables: [], texts: [] };

    act(() => {
      result.current.setPendingArtifacts(artifacts);
    });
    expect(result.current.pendingArtifacts).toEqual(artifacts);
  });

  it("sets active session id", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.setActiveSessionId("ses-123");
    });
    expect(result.current.activeSessionId).toBe("ses-123");
  });
});

// ── Component tests (new: failure paths) ─────────────────────────────────────

const { useSessionsMock, useMessagesMock, useCreateSessionMock, useDeleteSessionMock } =
  vi.hoisted(() => ({
    useSessionsMock: vi.fn(),
    useMessagesMock: vi.fn(),
    useCreateSessionMock: vi.fn(),
    useDeleteSessionMock: vi.fn(),
  }));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => useSessionsMock(),
  useCreateSession: () => useCreateSessionMock(),
  useDeleteSession: () => useDeleteSessionMock(),
}));

vi.mock("../queries/useMessages", () => ({
  useMessages: () => useMessagesMock(),
}));

vi.mock("../lib/sse", () => ({
  streamChat: vi.fn(),
}));

import { streamChat } from "../lib/sse";
import { fireEvent } from "@testing-library/react";

vi.mock("../components/ChatMessage", () => ({
  default: ({ role, content }: { role: string; content: string }) => (
    <div data-testid={`msg-${role}`}>{content}</div>
  ),
}));

describe("ChatView component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    // The chat store is a global Zustand singleton — the hook tests above
    // (e.g. "sets streaming state") leave isStreaming=true behind, which
    // would render the composer as "..." and block turn simulation here.
    act(() => {
      useChatStore.setState({ isStreaming: false, streamingText: "", pendingArtifacts: null });
    });
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Chat 1" }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    useMessagesMock.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    useCreateSessionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ id: "ses-new", title: "New" }),
    });
    useDeleteSessionMock.mockReturnValue({ mutate: vi.fn() });
  });

  it("renders the session sidebar heading", () => {
    renderWithProviders(<ChatView />, { route: "/app/chat" });
    expect(screen.getByText("Chat 1")).toBeTruthy();
  });

  it("shows sessions error with retry (R-ErrorUI-3)", () => {
    useSessionsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load sessions"),
      refetch: vi.fn(),
    });
    renderWithProviders(<ChatView />, { route: "/app/chat" });
    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("shows messages error with retry (R-ErrorUI-3)", () => {
    useMessagesMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load chat messages"),
      refetch: vi.fn(),
    });
    renderWithProviders(<ChatView />, { route: "/app/chat/ses-1" });
    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("failed turn shows chat error with a Retry-turn button", async () => {
    vi.mocked(streamChat).mockImplementation(async (_sid, _q, handlers) => {
      handlers.onError?.("LLMTimeoutError", "boom");
    });
    renderWithProviders(<ChatView />, {
      route: "/app/chat/ses-1",
      path: "/app/chat/:sessionId",
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask a question/), {
      target: { value: "mi pregunta" },
    });
    fireEvent.click(screen.getByText("Send"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("LLMTimeoutError");
    // The chat-error Retry button (distinct from ErrorCard retry buttons)
    const retryButtons = await screen.findAllByText("Retry");
    expect(retryButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("clicking Retry re-runs the failed turn with retry=true (no question duplication)", async () => {
    vi.mocked(streamChat)
      .mockImplementationOnce(async (_sid, _q, handlers) => {
        handlers.onError?.("LLMTimeoutError", "boom");
      })
      .mockImplementationOnce(async (_sid, _q, handlers) => {
        handlers.onDone?.(1);
      });
    renderWithProviders(<ChatView />, {
      route: "/app/chat/ses-1",
      path: "/app/chat/:sessionId",
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask a question/), {
      target: { value: "mi pregunta" },
    });
    fireEvent.click(screen.getByText("Send"));
    await screen.findByRole("alert");

    vi.mocked(streamChat).mockClear();
    fireEvent.click(screen.getAllByText("Retry")[0]);

    await waitFor(() =>
      expect(streamChat).toHaveBeenCalledWith(
        "ses-1",
        "mi pregunta",
        expect.anything(),
        expect.anything(),
        true // retry flag — server must NOT re-persist the question
      ),
    );
  });
});